#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Airael dataset capture: time-matched thermal + RGB pairs with drone pose.

Command-line alternative to dataset_server.py (which is driven from the ground-station Dataset tab).

Each run creates its own session folder:
  ~/dataset/<session>/thermal/<stamp_ms>.png   raw thermal frame (no rescaling)
  ~/dataset/<session>/rgb/<stamp_ms>.png       RGB frame matched by timestamp
  ~/dataset/<session>/index.csv                stamps, files, pose, visible ArUco ids
  ~/dataset/<session>/session.txt              settings and notes

Run (ROS already running):
  python3 ~/airael/dataset_capture.py _session:=bonfire_h15 _rate:=2 _note:="bonfire at 1.5 m, warm"
Stop with Ctrl+C: files are written atomically, so no empty images are left.

Params (all optional):
  ~session      name of the session folder (default: date_time)
  ~rate         max saved pairs per second (default 2)
  ~min_diff     skip a frame whose thermal image differs from the last saved one by
                less than this mean grey level (0-255). 0 = keep everything. Default 1.5
  ~thermal_topic, ~rgb_topic, ~pose_topic, ~markers_topic
  ~slop         max time difference between thermal and RGB frames, s (default 0.04)
  ~thermal_only true = do not wait for / save RGB (default false)
  ~note         free text stored in session.txt
  ~range_topic  rangefinder (sensor_msgs/Range), default /rangefinder/range
  ~min_alt, ~max_alt  only save frames with altitude inside this range, m
                (default 0 and 100 = save everything; e.g. _min_alt:=0.5 skips take-off and landing)

Altitude = rangefinder distance x cos(tilt) = height above the floor under the drone.
If the rangefinder has no valid reading, the local-position z is used (alt_source column).
"""

import csv
import math
import os
import shutil
import time

import cv2
import message_filters
import numpy as np
import rospy
from cv_bridge import CvBridge
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Image, Range

try:
    from aruco_pose.msg import MarkerArray
except ImportError:  # aruco_pose not on this image: marker ids are left empty
    MarkerArray = None

MIN_FREE_BYTES = 500 * 1024 * 1024


def yaw_from_quat(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def cos_tilt(q):
    """Cosine of the angle between the body z axis and the vertical."""
    return 1.0 - 2.0 * (q.x * q.x + q.y * q.y)


def write_png_atomic(path, img):
    ok, buf = cv2.imencode('.png', img)
    if not ok:
        raise IOError('PNG encode failed')
    tmp = path + '.tmp'
    with open(tmp, 'wb') as f:
        f.write(buf.tobytes())
    os.replace(tmp, path)


def small_gray(img):
    g = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if g.dtype != np.uint8:  # 16-bit thermal: compare on a fixed 8-bit view
        g = (g >> 8).astype(np.uint8)
    return cv2.resize(g, (64, 48), interpolation=cv2.INTER_AREA).astype(np.int16)


class Capture:
    def __init__(self):
        rospy.init_node('dataset_capture', anonymous=True)
        self.session = rospy.get_param('~session', time.strftime('%Y%m%d_%H%M%S'))
        self.root = os.path.expanduser(rospy.get_param('~root', '~/dataset'))
        self.period = 1.0 / max(0.1, float(rospy.get_param('~rate', 2.0)))
        self.min_diff = float(rospy.get_param('~min_diff', 1.5))
        self.thermal_only = bool(rospy.get_param('~thermal_only', False))
        t_topic = rospy.get_param('~thermal_topic', '/second_camera/second_camera/image_raw')
        r_topic = rospy.get_param('~rgb_topic', '/main_camera/image_raw')
        p_topic = rospy.get_param('~pose_topic', '/mavros/local_position/pose')
        m_topic = rospy.get_param('~markers_topic', '/aruco_detect/markers')
        slop = float(rospy.get_param('~slop', 0.04))
        rng_topic = rospy.get_param('~range_topic', '/rangefinder/range')
        self.min_alt = float(rospy.get_param('~min_alt', 0.0))
        self.max_alt = float(rospy.get_param('~max_alt', 100.0))

        self.dir = os.path.join(self.root, self.session)
        self.tdir = os.path.join(self.dir, 'thermal')
        self.rdir = os.path.join(self.dir, 'rgb')
        os.makedirs(self.tdir, exist_ok=True)
        if not self.thermal_only:
            os.makedirs(self.rdir, exist_ok=True)

        with open(os.path.join(self.dir, 'session.txt'), 'a') as f:
            f.write('started %s\nthermal %s\nrgb %s\nrangefinder %s\nrate %.2f Hz  min_diff %.1f  slop %.3f s  '
                    'altitude %.2f-%.2f m\nnote %s\n\n' % (
                        time.strftime('%Y-%m-%d %H:%M:%S'), t_topic, 'off' if self.thermal_only else r_topic,
                        rng_topic, 1.0 / self.period, self.min_diff, slop, self.min_alt, self.max_alt,
                        rospy.get_param('~note', '')))

        new_csv = not os.path.exists(os.path.join(self.dir, 'index.csv'))
        self.csv_f = open(os.path.join(self.dir, 'index.csv'), 'a', newline='')
        self.csv = csv.writer(self.csv_f)
        if new_csv:
            self.csv.writerow(['thermal_file', 'rgb_file', 'thermal_stamp', 'rgb_stamp', 'dt_ms',
                               'alt_m', 'alt_source', 'alt_band_m', 'range_raw_m',
                               'x', 'y', 'z', 'yaw_deg', 'pose_age_s', 'aruco_ids',
                               'thermal_w', 'thermal_h', 'thermal_encoding'])

        self.bridge = CvBridge()
        self.pose = None
        self.pose_t = 0.0
        self.ids = ''
        self.rng = None
        self.rng_t = 0.0
        self.skipped_alt = 0
        self.ids_t = 0.0
        self.last_save = 0.0
        self.last_small = None
        self.saved = self.skipped = 0

        rospy.Subscriber(p_topic, PoseStamped, self.pose_cb, queue_size=1)
        rospy.Subscriber(rng_topic, Range, self.range_cb, queue_size=1)
        if MarkerArray is not None:
            rospy.Subscriber(m_topic, MarkerArray, self.markers_cb, queue_size=1)

        if self.thermal_only:
            rospy.Subscriber(t_topic, Image, lambda t: self.pair_cb(t, None), queue_size=1, buff_size=2 ** 22)
        else:
            ts = message_filters.ApproximateTimeSynchronizer(
                [message_filters.Subscriber(t_topic, Image, buff_size=2 ** 22),
                 message_filters.Subscriber(r_topic, Image, buff_size=2 ** 24)],
                queue_size=10, slop=slop)
            ts.registerCallback(self.pair_cb)
        rospy.loginfo('dataset_capture: saving to %s (%s)', self.dir,
                      'thermal only' if self.thermal_only else 'thermal + rgb')
        rospy.on_shutdown(self.close)

    def pose_cb(self, m):
        self.pose, self.pose_t = m.pose, time.time()

    def range_cb(self, m):
        if m.min_range <= m.range <= m.max_range and math.isfinite(m.range):
            self.rng, self.rng_t = m.range, time.time()

    def altitude(self, now):
        """(altitude m, source, raw range) - rangefinder corrected for tilt, else local z."""
        p = self.pose
        if self.rng is not None and now - self.rng_t < 0.5:
            c = cos_tilt(p.orientation) if p is not None else 1.0
            return self.rng * max(0.0, c), 'rangefinder', self.rng
        if p is not None and now - self.pose_t < 0.5:
            return p.position.z, 'local_z', None
        return None, 'none', None

    def markers_cb(self, m):
        self.ids = ' '.join(str(mk.id) for mk in m.markers)
        self.ids_t = time.time()

    def pair_cb(self, t_msg, r_msg):
        now = time.time()
        if now - self.last_save < self.period:
            return
        if shutil.disk_usage(self.dir).free < MIN_FREE_BYTES:
            rospy.logerr_throttle(10, 'dataset_capture: less than 500 MB free, not saving')
            return
        try:
            thermal = self.bridge.imgmsg_to_cv2(t_msg, desired_encoding='passthrough')  # raw, no rescaling
            rgb = self.bridge.imgmsg_to_cv2(r_msg, desired_encoding='bgr8') if r_msg is not None else None
        except Exception as e:  # noqa: BLE001
            rospy.logwarn_throttle(5, 'cv_bridge: %s', e)
            return

        alt, alt_src, rng_raw = self.altitude(now)
        if alt is not None and not (self.min_alt <= alt <= self.max_alt):
            self.skipped_alt += 1
            return
        if alt is None and (self.min_alt > 0 or self.max_alt < 100):
            rospy.logwarn_throttle(5, 'no altitude (rangefinder or pose): frame not saved because of the altitude limits')
            self.skipped_alt += 1
            return

        small = small_gray(thermal)
        if self.min_diff > 0 and self.last_small is not None and \
                float(np.mean(np.abs(small - self.last_small))) < self.min_diff:
            self.skipped += 1
            return

        name = '%d.png' % int(round(t_msg.header.stamp.to_sec() * 1000))
        try:
            write_png_atomic(os.path.join(self.tdir, name), thermal)
            if rgb is not None:
                write_png_atomic(os.path.join(self.rdir, name), rgb)
        except Exception as e:  # noqa: BLE001
            rospy.logerr('write failed: %s', e)
            return

        p = self.pose
        fresh_ids = self.ids if now - self.ids_t < 0.5 else ''
        self.csv.writerow([
            'thermal/' + name, ('rgb/' + name) if rgb is not None else '',
            '%.3f' % t_msg.header.stamp.to_sec(),
            '%.3f' % r_msg.header.stamp.to_sec() if r_msg is not None else '',
            '%.1f' % ((r_msg.header.stamp - t_msg.header.stamp).to_sec() * 1000) if r_msg is not None else '',
            '%.3f' % alt if alt is not None else '', alt_src,
            '%.1f' % (round(alt * 2) / 2.0) if alt is not None else '',
            '%.3f' % rng_raw if rng_raw is not None else '',
            '%.3f' % p.position.x if p else '', '%.3f' % p.position.y if p else '',
            '%.3f' % p.position.z if p else '',
            '%.1f' % math.degrees(yaw_from_quat(p.orientation)) if p else '',
            '%.2f' % (now - self.pose_t) if p else '',
            fresh_ids, thermal.shape[1], thermal.shape[0], t_msg.encoding])
        self.csv_f.flush()
        self.last_small, self.last_save = small, now
        self.saved += 1
        if self.saved % 10 == 0:
            rospy.loginfo('saved %d pairs at %s m (%s); skipped %d near-duplicates, %d outside altitude -> %s',
                          self.saved, '%.2f' % alt if alt is not None else '?', alt_src,
                          self.skipped, self.skipped_alt, self.dir)

    def close(self):
        try:
            self.csv_f.close()
        except Exception:  # noqa: BLE001
            pass
        for d in (self.tdir, self.rdir):  # remove half-written files, if any
            if os.path.isdir(d):
                for f in os.listdir(d):
                    if f.endswith('.tmp'):
                        os.remove(os.path.join(d, f))
        with open(os.path.join(self.dir, 'session.txt'), 'a') as f:
            f.write('stopped %s  saved %d  skipped %d duplicates, %d outside altitude\n' % (
                time.strftime('%Y-%m-%d %H:%M:%S'), self.saved, self.skipped, self.skipped_alt))
        print('dataset_capture: %d pairs saved, %d near-duplicates and %d outside altitude skipped, in %s' % (
            self.saved, self.skipped, self.skipped_alt, self.dir))


if __name__ == '__main__':
    Capture()
    rospy.spin()
