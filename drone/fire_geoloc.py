#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Airael geolocation: detector boxes (pixels) -> object positions on the ArUco map (metres).

In : /fire/detections (std_msgs/String JSON from fire_detector_node.py: stamp, width, height,
     detections[{class_name, score, bbox, center}])
     <camera_info> (sensor_msgs/CameraInfo): intrinsics and distortion of the detector's camera
     tf: <map_frame> <- <camera optical frame> at the image time (Skyris publishes both)
Out: /fire/events (std_msgs/String JSON, read by the ground station):
     {"stamp", "class_name", "score", "x", "y", "id", "kind": "new"|"update", "hits", "spread", "cam_z", "plane_z"}
     /fire/objects (std_msgs/String JSON, latched): all tracked objects

Method: a ray from the camera centre through the box centre (undistorted with camera_info) is turned
into the map frame with tf and intersected with a horizontal plane at the object's height
(~object_heights, e.g. campfire 0.15 m, tree 0.6 m). Sightings of the same class closer than
~merge_radius are one object; its position is the median of the last sightings.
An object is reported ("new") after ~min_hits sightings within 1.5 s, then again ("update")
every ~update_period s while it is still seen, with the refined position.

Run on the drone (detector running):
  python3 ~/airael/fire_geoloc.py                                   # RGB camera (default)
  python3 ~/airael/fire_geoloc.py _camera_info:=/second_camera/second_camera/camera_info _hfov_deg:=56   # thermal
Reset the tracked objects: rostopic pub -1 /fire/reset std_msgs/Empty
"""

import json
import math
import threading
import time

import numpy as np
import rospy
from sensor_msgs.msg import CameraInfo
from std_msgs.msg import Empty, String

try:
    import cv2
except ImportError:  # undistortion is skipped without OpenCV
    cv2 = None
import tf2_ros


# ---------------------------------------------------------------- pure geometry (unit-tested)
def quat_to_mat(x, y, z, w):
    n = math.sqrt(x * x + y * y + z * z + w * w) or 1.0
    x, y, z, w = x / n, y / n, z / n, w / n
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def pixel_to_ray(u, v, K, D=None, model='plumb_bob'):
    """Pixel -> unit-less ray (xn, yn, 1) in the camera optical frame (x right, y down, z forward)."""
    if cv2 is not None and D is not None and len(D) and any(abs(d) > 1e-9 for d in D):
        pts = np.array([[[u, v]]], dtype=np.float64)
        if model == 'equidistant':
            n = cv2.fisheye.undistortPoints(pts, K, np.array(D[:4], dtype=np.float64))
        else:
            n = cv2.undistortPoints(pts, K, np.array(D, dtype=np.float64))
        xn, yn = float(n[0, 0, 0]), float(n[0, 0, 1])
    else:
        xn, yn = (u - K[0, 2]) / K[0, 0], (v - K[1, 2]) / K[1, 1]
    return np.array([xn, yn, 1.0])


def ray_to_plane(origin, R, ray_cam, plane_z):
    """Intersect the ray (camera origin + R @ ray_cam * t) with the plane z = plane_z. None if it misses."""
    d = R @ ray_cam
    if d[2] > -1e-6:          # ray does not point down
        return None
    t = (plane_z - origin[2]) / d[2]
    if t <= 0:
        return None
    return origin + t * d


class Tracker:
    """Merges sightings of the same class within merge_radius into one object."""

    def __init__(self, merge_radius=0.6, min_hits=2, confirm_window=1.5, update_period=2.0, keep=15):
        self.r, self.min_hits, self.win, self.period, self.keep = merge_radius, min_hits, confirm_window, update_period, keep
        self.objs = []
        self.next_id = 1

    def add(self, cls, x, y, score, stamp, now):
        """Returns ('new'|'update', obj) when an event should be published, else (None, obj)."""
        best, bd = None, self.r
        for o in self.objs:
            if o['cls'] != cls:
                continue
            d = math.hypot(o['x'] - x, o['y'] - y)
            if d <= bd:
                best, bd = o, d
        if best is None:
            best = {'id': None, 'cls': cls, 'pts': [], 'x': x, 'y': y, 'score': 0.0, 'hits': 0,
                    'first': now, 'last_seen': now, 'last_pub': 0.0, 'confirmed': False}
            self.objs.append(best)
        o = best
        if not o['confirmed'] and now - o['last_seen'] > self.win:   # stale candidate: start over
            o['pts'], o['hits'], o['first'] = [], 0, now
        o['pts'] = (o['pts'] + [(x, y)])[-self.keep:]
        o['x'] = float(np.median([p[0] for p in o['pts']]))
        o['y'] = float(np.median([p[1] for p in o['pts']]))
        o['hits'] += 1
        o['score'] = max(o['score'], score)
        o['last_seen'], o['stamp'] = now, stamp
        if not o['confirmed']:
            if o['hits'] >= self.min_hits:
                o['confirmed'], o['id'], o['last_pub'] = True, self.next_id, now
                self.next_id += 1
                return 'new', o
            return None, o
        if now - o['last_pub'] >= self.period:
            o['last_pub'] = now
            return 'update', o
        return None, o

    def spread(self, o):
        if len(o['pts']) < 2:
            return 0.0
        return float(max(math.hypot(px - o['x'], py - o['y']) for px, py in o['pts']))

    def confirmed(self):
        return [o for o in self.objs if o['confirmed']]


# ---------------------------------------------------------------- node
class GeoLoc:
    def __init__(self):
        rospy.init_node('fire_geoloc')
        p = lambda n, d: rospy.get_param('~' + n, d)   # noqa: E731
        self.map_frame = p('map_frame', 'aruco_map')
        self.odom_frame = p('odom_frame', 'map')   # the drone's continuous frame; aruco_map is linked to it only while markers are seen
        self.link = None                          # last known (R, t, time) of map_frame <- odom_frame
        self.cam_frame_param = p('camera_frame', '')          # '' = take it from camera_info
        self.min_score = float(p('min_score', 0.5))
        heights = p('object_heights', {'campfire': 0.15, 'bonfire': 0.15, 'fire': 0.15, 'tree': 0.6})
        self.heights = {str(k).lower(): float(v) for k, v in (heights or {}).items()}
        self.default_h = float(p('default_height', 0.0))
        self.hfov = float(p('hfov_deg', 0.0))                  # used only if camera_info has no intrinsics
        self.tracker = Tracker(float(p('merge_radius', 0.6)), int(p('min_hits', 2)),
                               1.5, float(p('update_period', 2.0)))
        self.lock = threading.Lock()
        self.K = self.D = None
        self.model, self.ci_size, self.ci_frame = 'plumb_bob', None, ''
        self.stats = {'dets': 0, 'located': 0, 'tf_fail': 0, 'miss': 0, 'events': 0}

        self.tf_buf = tf2_ros.Buffer(rospy.Duration(10.0))
        self.tf_listener = tf2_ros.TransformListener(self.tf_buf)
        self.pub = rospy.Publisher(p('events_topic', '/fire/events'), String, queue_size=20)
        self.pub_objs = rospy.Publisher(p('objects_topic', '/fire/objects'), String, queue_size=1, latch=True)
        rospy.Subscriber(p('camera_info', '/main_camera/camera_info'), CameraInfo, self.ci_cb, queue_size=1)
        rospy.Subscriber(p('detections_topic', '/fire/detections'), String, self.det_cb, queue_size=5)
        rospy.Subscriber('/fire/reset', Empty, self.reset_cb, queue_size=1)
        rospy.Timer(rospy.Duration(10.0), self.report)
        rospy.loginfo('fire_geoloc: %s -> %s, heights %s, camera_info %s', p('detections_topic', '/fire/detections'),
                      self.map_frame, self.heights, p('camera_info', '/main_camera/camera_info'))

    def ci_cb(self, m):
        K = np.array(m.K, dtype=np.float64).reshape(3, 3)
        if K[0, 0] <= 0 or K[1, 1] <= 0:
            K = None
        with self.lock:
            self.K, self.D = K, list(m.D)
            self.model = m.distortion_model or 'plumb_bob'
            self.ci_size, self.ci_frame = (m.width, m.height), m.header.frame_id

    def reset_cb(self, _m):
        with self.lock:
            self.tracker = Tracker(self.tracker.r, self.tracker.min_hits, self.tracker.win, self.tracker.period)
        self.pub_objs.publish(String(data='[]'))
        rospy.loginfo('fire_geoloc: tracked objects cleared')

    def intrinsics(self, w, h):
        """K for an image of w x h: camera_info scaled to the detector's image size, or from hfov."""
        with self.lock:
            K, D, model, size = self.K, self.D, self.model, self.ci_size
        if K is not None and size and size[0] > 0:
            sx, sy = w / float(size[0]), h / float(size[1])
            K = K.copy()
            K[0, :] *= sx
            K[1, :] *= sy
            return K, D, model
        if self.hfov > 0:
            f = (w / 2.0) / math.tan(math.radians(self.hfov) / 2.0)
            return np.array([[f, 0, w / 2.0], [0, f, h / 2.0], [0, 0, 1.0]]), None, 'plumb_bob'
        return None, None, None

    def det_cb(self, msg):
        try:
            d = json.loads(msg.data)
        except ValueError:
            return
        dets = [x for x in d.get('detections', []) if float(x.get('score', 0)) >= self.min_score]
        if not dets:
            return
        w, h = int(d.get('width', 0)), int(d.get('height', 0))
        K, D, model = self.intrinsics(w, h)
        if K is None:
            rospy.logwarn_throttle(10, 'fire_geoloc: no camera intrinsics (camera_info empty and hfov_deg not set)')
            return
        cam_frame = self.cam_frame_param or self.ci_frame
        if not cam_frame:
            rospy.logwarn_throttle(10, 'fire_geoloc: no camera frame yet (waiting for camera_info or set ~camera_frame)')
            return
        stamp = float(d.get('stamp', 0.0))
        pose = self.camera_pose(cam_frame, stamp)
        if pose is None:
            return
        R, origin = pose
        now = time.time()
        objs_changed = False
        for x in dets:
            self.stats['dets'] += 1
            cls = str(x.get('class_name', '?'))
            cx, cy = x.get('center') or [(x['bbox'][0] + x['bbox'][2]) / 2.0, (x['bbox'][1] + x['bbox'][3]) / 2.0]
            plane = self.heights.get(cls.lower(), self.default_h)
            ray = pixel_to_ray(float(cx), float(cy), K, D, model)
            pt = ray_to_plane(origin, R, ray, plane)
            if pt is None:
                self.stats['miss'] += 1
                dz = float((R @ ray)[2])
                if origin[2] <= plane:
                    why = 'camera is only %.2f m above the marker floor, below the %s plane (%.2f m): hold/fly higher' % (origin[2], cls, plane)
                else:
                    why = 'camera ray does not point down (z component %+.2f): is the camera facing the floor?' % dz
                rospy.logwarn_throttle(3, 'fire_geoloc: %s not located: %s', cls, why)
                continue
            self.stats['located'] += 1
            with self.lock:
                kind, o = self.tracker.add(cls, float(pt[0]), float(pt[1]), float(x.get('score', 0)), stamp, now)
                spread = self.tracker.spread(o)
            if kind:
                ev = {'stamp': stamp, 'class_name': cls, 'score': round(o['score'], 3), 'x': round(o['x'], 3),
                      'y': round(o['y'], 3), 'id': o['id'], 'kind': kind, 'hits': o['hits'], 'spread': round(spread, 3),
                      'cam_z': round(float(origin[2]), 3), 'plane_z': plane}
                self.pub.publish(String(data=json.dumps(ev)))
                self.stats['events'] += 1
                objs_changed = True
                if kind == 'new':
                    rospy.loginfo('fire_geoloc: NEW %s #%d at (%.2f, %.2f), camera z %.2f m', cls, o['id'], o['x'], o['y'], origin[2])
        if objs_changed:
            self.publish_objects()

    def lookup(self, target, source, stamp):
        """(R, t) of target <- source at the image time, else the latest; None if there is no path."""
        errs = (tf2_ros.LookupException, tf2_ros.ConnectivityException, tf2_ros.ExtrapolationException)
        for when, wait in ((rospy.Time.from_sec(stamp), 0.15), (rospy.Time(0), 0.05)):
            try:
                tf = self.tf_buf.lookup_transform(target, source, when, rospy.Duration(wait))
                t, q = tf.transform.translation, tf.transform.rotation
                return quat_to_mat(q.x, q.y, q.z, q.w), np.array([t.x, t.y, t.z])
            except errs:
                continue
        return None

    def camera_pose(self, cam_frame, stamp):
        """Camera pose in map_frame. Direct when markers are seen; otherwise the drone's pose in odom_frame
        combined with the last known map_frame <- odom_frame link (it changes only slowly)."""
        direct = self.lookup(self.map_frame, cam_frame, stamp)
        link = self.lookup(self.map_frame, self.odom_frame, stamp)
        if link is not None:
            self.link = (link[0], link[1], time.time())
        if direct is not None:
            return direct
        if self.link is None:
            self.stats['tf_fail'] += 1
            rospy.logwarn_throttle(5, 'fire_geoloc: no %s -> %s yet: fly where the camera sees ArUco markers once', cam_frame, self.map_frame)
            return None
        cam = self.lookup(self.odom_frame, cam_frame, stamp)
        if cam is None:
            self.stats['tf_fail'] += 1
            rospy.logwarn_throttle(5, 'fire_geoloc: no transform %s -> %s', cam_frame, self.odom_frame)
            return None
        R1, t1, at = self.link
        self.stats['via_link'] = self.stats.get('via_link', 0) + 1
        age = time.time() - at
        if age > 30:
            rospy.logwarn_throttle(10, 'fire_geoloc: markers not seen for %.0f s, positions use the last marker fix (may drift)', age)
        return R1 @ cam[0], R1 @ cam[1] + t1

    def publish_objects(self):
        with self.lock:
            objs = [{'id': o['id'], 'class_name': o['cls'], 'x': round(o['x'], 3), 'y': round(o['y'], 3),
                     'hits': o['hits'], 'score': round(o['score'], 3), 'spread': round(self.tracker.spread(o), 3)}
                    for o in self.tracker.confirmed()]
        self.pub_objs.publish(String(data=json.dumps(objs)))

    def report(self, _e):
        s = self.stats
        if s['dets']:
            rospy.loginfo('fire_geoloc: %d detections, %d located, %d tf failures, %d rays missed the floor, %d events, %d objects',
                          s['dets'], s['located'], s['tf_fail'], s['miss'], s['events'], len(self.tracker.confirmed()))


if __name__ == '__main__':
    GeoLoc()
    rospy.spin()
