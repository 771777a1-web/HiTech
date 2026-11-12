#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Airael dataset server: start and stop dataset capture from the ground-station page.

Commands arrive on /airael/dataset/cmd (std_msgs/String, JSON):
  {"cmd": "start", "id": "a1", "label": "bonfire", "session": "",   # session empty = <label>_<date>_<time>
   "rate": 2, "min_alt": 0.3, "max_alt": 3.0, "min_diff": 1.5, "rgb": true, "note": "..."}
  {"cmd": "stop", "id": "a2"}
  {"cmd": "ping", "id": "a3"}
  {"cmd": "capture", "id": "a4", "class_name": "campfire", "object_id": 3, "score": 0.91,
   "x": 1.2, "y": -0.5, "z": 1.0, "dedup_radius": 0.75, "note": "route inspection"}
A start while recording closes the current session and opens the new one.

capture saves one photo of what the drone sees now (for the ground station's Detections tab):
  ~/ground_station/captures/<date>_<time>_<class>_<id>/rgb.jpg       RGB frame with the latest detector boxes
  ~/ground_station/captures/<date>_<time>_<class>_<id>/rgb_raw.jpg   the same frame without boxes
  ~/ground_station/captures/<date>_<time>_<class>_<id>/thermal.png   thermal frame (raw)
  ~/ground_station/captures/<date>_<time>_<class>_<id>/meta.json     class, score, object id, map x/y, altitude, time
  ~/ground_station/captures/index.json                               all captures, newest first
The page server (port 8020) serves these files. A capture of the same class closer than dedup_radius (m)
to an earlier one is refused as a duplicate (dedup_radius 0 = always capture).

Status goes out on /airael/dataset/status (std_msgs/String, JSON) once a second and after every
saved frame. "ack" echoes the id of the last command handled.

Folder layout is the same as dataset_capture.py, plus a label:
  ~/dataset/<session>/thermal/<stamp_ms>.png   raw thermal frame (no rescaling)
  ~/dataset/<session>/rgb/<stamp_ms>.png       RGB frame matched by timestamp (if rgb is on)
  ~/dataset/<session>/index.csv                stamps, files, altitude, pose, visible ArUco ids, label
  ~/dataset/<session>/session.txt              settings and notes
  ~/dataset/<session>/meta.json                {"label": ...}

The cameras are only subscribed while recording, so the node costs almost nothing when idle.

Run on the drone (ROS already running); airael.sh start does this for you:
  python3 ~/airael/dataset_server.py
"""

import csv
import json
import math
import os
import re
import shutil
import threading
import time

import cv2
import message_filters
import numpy as np
import rospy
from cv_bridge import CvBridge
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Image, Range
from std_msgs.msg import String

try:
    from aruco_pose.msg import MarkerArray
except ImportError:  # aruco_pose not on this image: marker ids are left empty
    MarkerArray = None

MIN_FREE_BYTES = 500 * 1024 * 1024
CSV_HEADER = ['thermal_file', 'rgb_file', 'thermal_stamp', 'rgb_stamp', 'dt_ms',
              'alt_m', 'alt_source', 'alt_band_m', 'range_raw_m',
              'x', 'y', 'z', 'yaw_deg', 'pose_age_s', 'aruco_ids',
              'thermal_w', 'thermal_h', 'thermal_encoding', 'label']


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


def clean_name(s, default):
    s = re.sub(r'[^A-Za-z0-9_.+-]+', '_', str(s or '').strip()).strip('._')
    return (s or default)[:64]


def band_key(alt):
    return '%.1f' % (round(alt * 2) / 2.0)


class Session:
    """One recording: files, csv, counters. Created on start, closed on stop."""

    def __init__(self, root, name, label, opts, topics):
        self.name, self.label, self.opts = name, label, opts
        self.dir = os.path.join(root, name)
        self.tdir = os.path.join(self.dir, 'thermal')
        self.rdir = os.path.join(self.dir, 'rgb')
        os.makedirs(self.tdir, exist_ok=True)
        if opts['rgb']:
            os.makedirs(self.rdir, exist_ok=True)
        with open(os.path.join(self.dir, 'meta.json'), 'w') as f:
            json.dump({'label': label}, f)
        with open(os.path.join(self.dir, 'session.txt'), 'a') as f:
            f.write('started %s (dataset_server)\nlabel %s\nthermal %s\nrgb %s\nrangefinder %s\n'
                    'rate %.2f Hz  min_diff %.1f  slop %.3f s  altitude %.2f-%.2f m\nnote %s\n\n' % (
                        time.strftime('%Y-%m-%d %H:%M:%S'), label, topics['thermal'],
                        topics['rgb'] if opts['rgb'] else 'off', topics['range'], opts['rate'],
                        opts['min_diff'], opts['slop'], opts['min_alt'], opts['max_alt'], opts['note']))
        new_csv = not os.path.exists(os.path.join(self.dir, 'index.csv'))
        self.csv_f = open(os.path.join(self.dir, 'index.csv'), 'a', newline='')
        self.csv = csv.writer(self.csv_f)
        if new_csv:
            self.csv.writerow(CSV_HEADER)
        self.started = time.time()
        self.saved = self.skipped_dup = self.skipped_alt = 0
        self.bands = {}
        self.last_save = 0.0
        self.last_small = None
        self.last_pair = 0.0
        self.last_file = ''

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
                time.strftime('%Y-%m-%d %H:%M:%S'), self.saved, self.skipped_dup, self.skipped_alt))


class DatasetServer:
    def __init__(self):
        rospy.init_node('airael_dataset_server')
        self.root = os.path.expanduser(rospy.get_param('~root', '~/dataset'))
        self.topics = {
            'thermal': rospy.get_param('~thermal_topic', '/second_camera/second_camera/image_raw'),
            'rgb': rospy.get_param('~rgb_topic', '/main_camera/image_raw'),
            'pose': rospy.get_param('~pose_topic', '/mavros/local_position/pose'),
            'markers': rospy.get_param('~markers_topic', '/aruco_detect/markers'),
            'range': rospy.get_param('~range_topic', '/rangefinder/range'),
        }
        self.slop = float(rospy.get_param('~slop', 0.04))
        os.makedirs(self.root, exist_ok=True)
        self.cap_dir = os.path.expanduser(rospy.get_param('~captures_dir', '~/ground_station/captures'))
        os.makedirs(self.cap_dir, exist_ok=True)
        self.captures = self.load_captures()
        self.last_capture = {}
        self.last_dets, self.last_dets_t = None, 0.0

        self.lock = threading.RLock()
        self.bridge = CvBridge()
        self.sess = None
        self.cam_subs = []
        self.ack = ''
        self.error = ''
        self.pose = None
        self.pose_t = 0.0
        self.rng = None
        self.rng_t = 0.0
        self.ids = ''
        self.ids_t = 0.0
        self.sessions_cache = []
        self.sessions_t = 0.0

        rospy.Subscriber(self.topics['pose'], PoseStamped, self.pose_cb, queue_size=1)
        rospy.Subscriber(self.topics['range'], Range, self.range_cb, queue_size=1)
        if MarkerArray is not None:
            rospy.Subscriber(self.topics['markers'], MarkerArray, self.markers_cb, queue_size=1)
        rospy.Subscriber(rospy.get_param('~detections_topic', '/fire/detections'), String, self.dets_cb, queue_size=1)
        self.pub = rospy.Publisher('/airael/dataset/status', String, queue_size=5, latch=True)
        rospy.Subscriber('/airael/dataset/cmd', String, self.cmd_cb, queue_size=10)
        rospy.Timer(rospy.Duration(1.0), lambda _e: self.publish())
        rospy.on_shutdown(self.shutdown)
        rospy.loginfo('airael_dataset_server ready: root %s, commands on /airael/dataset/cmd', self.root)
        self.publish()

    # ------------------------------------------------------------ inputs
    def pose_cb(self, m):
        self.pose, self.pose_t = m.pose, time.time()

    def range_cb(self, m):
        if m.min_range <= m.range <= m.max_range and math.isfinite(m.range):
            self.rng, self.rng_t = m.range, time.time()

    def dets_cb(self, m):
        try:
            self.last_dets, self.last_dets_t = json.loads(m.data), time.time()
        except ValueError:
            pass

    def markers_cb(self, m):
        self.ids = ' '.join(str(mk.id) for mk in m.markers)
        self.ids_t = time.time()

    def altitude(self, now):
        """(altitude m, source, raw range): rangefinder corrected for tilt, else local z."""
        p = self.pose
        if self.rng is not None and now - self.rng_t < 0.5:
            c = cos_tilt(p.orientation) if p is not None else 1.0
            return self.rng * max(0.0, c), 'rangefinder', self.rng
        if p is not None and now - self.pose_t < 0.5:
            return p.position.z, 'local_z', None
        return None, 'none', None

    # ------------------------------------------------------------ commands
    def cmd_cb(self, msg):
        try:
            c = json.loads(msg.data)
        except ValueError:
            self.error = 'bad command (not JSON)'
            self.publish()
            return
        cid = str(c.get('id', ''))
        if c.get('cmd') == 'capture':
            with self.lock:
                if cid and (cid == self.ack or cid == self.last_capture.get('id')):   # resend of a capture in progress/done
                    self.publish()
                    return
                self.last_capture = {'id': cid, 'status': 'capturing'}
            try:
                self.last_capture = dict(self.capture(c), id=cid)
                self.error = ''
            except Exception as e:  # noqa: BLE001
                self.last_capture = {'id': cid, 'status': 'error', 'error': str(e)}
                rospy.logerr('capture failed: %s', e)
            with self.lock:
                self.ack = cid
            self.publish()
            return
        with self.lock:
            if cid and cid == self.ack:   # the page may resend: handle each command once
                self.publish()
                return
            try:
                cmd = c.get('cmd')
                if cmd == 'start':
                    self.start(c)
                elif cmd == 'stop':
                    self.stop()
                elif cmd != 'ping':
                    raise ValueError('unknown command %r' % cmd)
                self.error = ''
            except Exception as e:  # noqa: BLE001
                self.error = str(e)
                rospy.logerr('dataset command failed: %s', e)
            self.ack = cid
        self.publish()

    def start(self, c):
        self.stop()
        label = clean_name(c.get('label'), 'unlabelled')
        name = clean_name(c.get('session'), '%s_%s' % (label, time.strftime('%Y%m%d_%H%M%S')))
        opts = {
            'rate': min(10.0, max(0.2, float(c.get('rate', 2.0)))),
            'min_alt': float(c.get('min_alt', 0.0)),
            'max_alt': float(c.get('max_alt', 100.0)),
            'min_diff': max(0.0, float(c.get('min_diff', 1.5))),
            'rgb': bool(c.get('rgb', True)),
            'note': str(c.get('note', ''))[:300],
            'slop': self.slop,
        }
        if shutil.disk_usage(self.root).free < MIN_FREE_BYTES:
            raise IOError('less than 500 MB free on the drone')
        self.sess = Session(self.root, name, label, opts, self.topics)
        if opts['rgb']:
            ts_sub = message_filters.Subscriber(self.topics['thermal'], Image, buff_size=2 ** 22)
            rgb_sub = message_filters.Subscriber(self.topics['rgb'], Image, buff_size=2 ** 24)
            ts = message_filters.ApproximateTimeSynchronizer([ts_sub, rgb_sub], queue_size=10, slop=self.slop)
            ts.registerCallback(self.pair_cb)
            self.cam_subs = [ts_sub, rgb_sub]
        else:
            self.cam_subs = [rospy.Subscriber(self.topics['thermal'], Image, lambda t: self.pair_cb(t, None),
                                              queue_size=1, buff_size=2 ** 22)]
        self.sessions_t = 0.0
        rospy.loginfo('dataset: recording %s (label %s, %.1f Hz, rgb %s) -> %s',
                      name, label, opts['rate'], opts['rgb'], self.sess.dir)

    def stop(self):
        for s in self.cam_subs:
            try:
                s.unregister()
            except Exception:  # noqa: BLE001
                pass
        self.cam_subs = []
        if self.sess is not None:
            s, self.sess = self.sess, None
            s.close()
            self.sessions_t = 0.0
            rospy.loginfo('dataset: stopped %s, %d saved', s.name, s.saved)

    # ------------------------------------------------------------ saving
    def pair_cb(self, t_msg, r_msg):
        now = time.time()
        with self.lock:
            s = self.sess
            if s is None:
                return
            s.last_pair = now
            if now - s.last_save < 1.0 / s.opts['rate']:
                return
            if shutil.disk_usage(s.dir).free < MIN_FREE_BYTES:
                self.error = 'less than 500 MB free: not saving'
                return
            try:
                thermal = self.bridge.imgmsg_to_cv2(t_msg, desired_encoding='passthrough')  # raw, no rescaling
                rgb = self.bridge.imgmsg_to_cv2(r_msg, desired_encoding='bgr8') if r_msg is not None else None
            except Exception as e:  # noqa: BLE001
                self.error = 'cv_bridge: %s' % e
                return

            alt, alt_src, rng_raw = self.altitude(now)
            limited = s.opts['min_alt'] > 0 or s.opts['max_alt'] < 100
            if (alt is not None and not (s.opts['min_alt'] <= alt <= s.opts['max_alt'])) or (alt is None and limited):
                s.skipped_alt += 1
                return
            small = small_gray(thermal)
            if s.opts['min_diff'] > 0 and s.last_small is not None and \
                    float(np.mean(np.abs(small - s.last_small))) < s.opts['min_diff']:
                s.skipped_dup += 1
                return

            name = '%d.png' % int(round(t_msg.header.stamp.to_sec() * 1000))
            try:
                write_png_atomic(os.path.join(s.tdir, name), thermal)
                if rgb is not None:
                    write_png_atomic(os.path.join(s.rdir, name), rgb)
            except Exception as e:  # noqa: BLE001
                self.error = 'write failed: %s' % e
                return

            p = self.pose
            fresh_ids = self.ids if now - self.ids_t < 0.5 else ''
            s.csv.writerow([
                'thermal/' + name, ('rgb/' + name) if rgb is not None else '',
                '%.3f' % t_msg.header.stamp.to_sec(),
                '%.3f' % r_msg.header.stamp.to_sec() if r_msg is not None else '',
                '%.1f' % ((r_msg.header.stamp - t_msg.header.stamp).to_sec() * 1000) if r_msg is not None else '',
                '%.3f' % alt if alt is not None else '', alt_src,
                band_key(alt) if alt is not None else '',
                '%.3f' % rng_raw if rng_raw is not None else '',
                '%.3f' % p.position.x if p else '', '%.3f' % p.position.y if p else '',
                '%.3f' % p.position.z if p else '',
                '%.1f' % math.degrees(yaw_from_quat(p.orientation)) if p else '',
                '%.2f' % (now - self.pose_t) if p else '',
                fresh_ids, thermal.shape[1], thermal.shape[0], t_msg.encoding, s.label])
            s.csv_f.flush()
            s.last_small, s.last_save, s.last_file = small, now, name
            s.saved += 1
            k = band_key(alt) if alt is not None else '?'
            s.bands[k] = s.bands.get(k, 0) + 1
        self.publish()

    # ------------------------------------------------------------ photo capture
    def load_captures(self):
        try:
            with open(os.path.join(self.cap_dir, 'index.json')) as f:
                d = json.load(f)
            return d if isinstance(d, list) else []
        except (OSError, ValueError):
            return []

    def save_index(self):
        tmp = os.path.join(self.cap_dir, 'index.json.tmp')
        with open(tmp, 'w') as f:
            json.dump(self.captures, f)
        os.replace(tmp, os.path.join(self.cap_dir, 'index.json'))

    def capture(self, c):
        cls = clean_name(c.get('class_name'), 'manual')
        def num(k):
            try:
                v = float(c.get(k))
                return v if math.isfinite(v) else None
            except (TypeError, ValueError):
                return None
        x, y, z, score = num('x'), num('y'), num('z'), num('score')
        radius = num('dedup_radius') or 0.0
        if radius > 0 and x is not None and y is not None:
            for e in self.captures:
                if e.get('class_name') == cls and e.get('x') is not None and \
                        math.hypot(e['x'] - x, e['y'] - y) < radius:
                    rospy.loginfo('capture: %s at (%.2f, %.2f) is a duplicate of %s', cls, x, y, e['name'])
                    return {'status': 'duplicate', 'of': e['name']}
        if shutil.disk_usage(self.cap_dir).free < MIN_FREE_BYTES:
            raise IOError('less than 500 MB free on the drone')
        rgb_msg = rospy.wait_for_message(self.topics['rgb'], Image, timeout=3.0)
        try:
            th_msg = rospy.wait_for_message(self.topics['thermal'], Image, timeout=1.5)
        except rospy.ROSException:
            th_msg = None
        rgb = self.bridge.imgmsg_to_cv2(rgb_msg, desired_encoding='bgr8')
        ann = rgb.copy()
        d, boxes = self.last_dets, 0
        if d and time.time() - self.last_dets_t < 1.0 and int(d.get('width', 0)) and int(d.get('height', 0)):
            sx, sy = rgb.shape[1] / float(d['width']), rgb.shape[0] / float(d['height'])
            if abs(sx - sy) < 0.02:   # same camera geometry (detector runs on this camera)
                for det in d.get('detections', []):
                    x1, y1, x2, y2 = [int(round(v * sx)) for v in det['bbox']]
                    col = (40, 110, 255) if 'fire' in det.get('class_name', '') else (90, 200, 60)
                    cv2.rectangle(ann, (x1, y1), (x2, y2), col, 2)
                    cv2.putText(ann, '%s %.2f' % (det.get('class_name', '?'), float(det.get('score', 0))),
                                (x1, max(14, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2, cv2.LINE_AA)
                    boxes += 1
        stamp = time.time()
        oid = c.get('object_id')
        name = '%s_%s%s' % (time.strftime('%Y%m%d_%H%M%S', time.localtime(stamp)), cls,
                            ('_%s' % clean_name(oid, '')) if oid not in (None, '') else '')
        cdir = os.path.join(self.cap_dir, name)
        os.makedirs(cdir, exist_ok=True)
        cv2.imwrite(os.path.join(cdir, 'rgb.jpg'), ann, [cv2.IMWRITE_JPEG_QUALITY, 90])
        cv2.imwrite(os.path.join(cdir, 'rgb_raw.jpg'), rgb, [cv2.IMWRITE_JPEG_QUALITY, 92])
        files = {'rgb': 'rgb.jpg', 'rgb_raw': 'rgb_raw.jpg'}
        if th_msg is not None:
            write_png_atomic(os.path.join(cdir, 'thermal.png'), self.bridge.imgmsg_to_cv2(th_msg, desired_encoding='passthrough'))
            files['thermal'] = 'thermal.png'
        alt, alt_src, _ = self.altitude(time.time())
        meta = {'name': name, 'time': stamp, 'time_iso': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(stamp)),
                'class_name': cls, 'object_id': oid, 'score': score, 'x': x, 'y': y, 'z': z,
                'alt': round(alt, 3) if alt is not None else None, 'alt_src': alt_src, 'boxes_drawn': boxes,
                'image_stamp': rgb_msg.header.stamp.to_sec(), 'note': str(c.get('note', ''))[:200], 'files': files}
        with open(os.path.join(cdir, 'meta.json'), 'w') as f:
            json.dump(meta, f, indent=1)
        with self.lock:
            self.captures.insert(0, meta)
            self.save_index()
        rospy.loginfo('capture: saved %s (%d boxes) -> %s', name, boxes, cdir)
        return {'status': 'saved', 'name': name}

    # ------------------------------------------------------------ status
    def sessions(self):
        """Session folders with frame counts and labels, newest first (refreshed every 5 s)."""
        now = time.time()
        if now - self.sessions_t < 5.0:
            return self.sessions_cache
        out = []
        try:
            for e in os.scandir(self.root):
                tdir = os.path.join(e.path, 'thermal')
                if not e.is_dir() or not os.path.isdir(tdir):
                    continue
                n = sum(1 for f in os.scandir(tdir) if f.name.endswith('.png'))
                label = ''
                try:
                    with open(os.path.join(e.path, 'meta.json')) as f:
                        label = json.load(f).get('label', '')
                except (OSError, ValueError):
                    pass
                out.append({'name': e.name, 'label': label, 'frames': n, 'mtime': e.stat().st_mtime})
        except OSError as e:
            self.error = 'cannot list %s: %s' % (self.root, e)
        out.sort(key=lambda d: d['mtime'], reverse=True)
        self.sessions_cache, self.sessions_t = out[:40], now
        return self.sessions_cache

    def publish(self):
        now = time.time()
        with self.lock:
            s = self.sess
            alt, alt_src, _ = self.altitude(now)
            st = {
                'stamp': now, 'ack': self.ack, 'error': self.error, 'root': self.root,
                'recording': s is not None,
                'alt': round(alt, 3) if alt is not None else None, 'alt_src': alt_src,
                'free_mb': int(shutil.disk_usage(self.root).free / 1e6),
                'sessions': [{k: d[k] for k in ('name', 'label', 'frames')} for d in self.sessions()],
                'captures': self.captures[:60], 'captures_total': len(self.captures),
                'last_capture': self.last_capture,
            }
            if s is not None:
                st.update({
                    'session': s.name, 'label': s.label, 'dir': s.dir, 'elapsed': round(now - s.started, 1),
                    'saved': s.saved, 'skipped_dup': s.skipped_dup, 'skipped_alt': s.skipped_alt,
                    'bands': s.bands, 'last_file': s.last_file, 'opts': s.opts,
                    'pair_age': round(now - s.last_pair, 1) if s.last_pair else None,
                })
        self.pub.publish(String(data=json.dumps(st)))

    def shutdown(self):
        with self.lock:
            self.stop()


if __name__ == '__main__':
    DatasetServer()
    rospy.spin()
