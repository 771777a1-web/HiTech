#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Airael fire detector: YOLOv8 (.rknn) on the RK3588 NPU.

Input : camera image topic (sensor_msgs/Image, bgr8). Default: the downward RGB camera
        /main_camera/image_raw (640x480), which the deployed campfire/tree model was trained on.
Output: JSON detections (std_msgs/String), one message per processed frame,
        also when nothing is detected; optional annotated image.

Based on the Skyris yolo_face_rknn_node.py (rknn-toolkit-lite2 2.3.0).
Changes against that node:
  * threshold params read correctly (conf_thres / iou_thres; *_thresh accepted too)
  * optional letterbox, as Ultralytics uses in training and val
  * optional min-max normalisation, to match how the dataset was captured
  * class-aware NMS, so a tree next to the fire is not suppressed
  * every frame is published with its stamp and processing time (needed for MC2-MC5)
  * annotated image is drawn only when someone subscribes (saves CPU)

JSON message on ~detections_topic:
{"stamp": 1794383745.64, "seq": 12, "width": 640, "height": 480, "proc_ms": 21.2,
 "detections": [{"class_id": 0, "class_name": "campfire", "score": 0.91,
                 "bbox": [x1, y1, x2, y2], "center": [cx, cy]}]}
bbox and center are in pixels of the original camera image.
"""

import os
import sys
import site
import logging

# --- environment fixes copied from the Skyris node (needed on this image) ---
os.environ['PYTHONNOUSERSITE'] = '1'
site.addsitedir('/opt/ros/noetic/lib/python3/dist-packages')
site.addsitedir('/usr/lib/python3/dist-packages')
for _p in ('/usr/local/lib/python3.8/dist-packages', '/usr/local/lib/python3/dist-packages'):
    if os.path.isdir(os.path.join(_p, 'rknnlite')):
        if _p in sys.path:
            sys.path.remove(_p)
        sys.path.insert(0, _p)
        break
os.environ.setdefault('LD_LIBRARY_PATH', '/usr/lib/aarch64-linux-gnu:/usr/lib:/usr/local/lib')
os.environ.pop('ROS_PYTHON_LOG_CONFIG_FILE', None)
import rosgraph.roslogging as _roslog  # noqa: E402


def _safe_configure_logging(name, level=None, filename=None):
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(name)s: %(message)s')
    return logging.getLogger(name)


_roslog.configure_logging = _safe_configure_logging

import json  # noqa: E402
import time  # noqa: E402
import numpy as np  # noqa: E402
import cv2  # noqa: E402
import rospy  # noqa: E402
from sensor_msgs.msg import Image  # noqa: E402
from std_msgs.msg import String  # noqa: E402
from cv_bridge import CvBridge  # noqa: E402

try:
    from rknnlite.api import RKNNLite
    import rknnlite.api.rknn_platform_utils  # noqa: F401
except ModuleNotFoundError as e:
    raise SystemExit('rknnlite incomplete (%s): pip package rknn-toolkit-lite2==2.3.0 is needed' % e)

log = logging.getLogger('fire_detector')


# ---------------------------------------------------------------- helpers
def letterbox(img, size, pad_value=114):
    """Resize keeping aspect ratio and pad to size x size (Ultralytics style)."""
    h, w = img.shape[:2]
    r = min(size / float(w), size / float(h))
    nw, nh = int(round(w * r)), int(round(h * r))
    px, py = (size - nw) // 2, (size - nh) // 2
    canvas = np.full((size, size, 3), pad_value, dtype=np.uint8)
    canvas[py:py + nh, px:px + nw] = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)
    return canvas, r, px, py


def decode(outputs, conf_thres):
    """YOLOv8 single-output head (1, 4+nc, N) -> boxes xyxy (input px), scores, class ids."""
    out = outputs[0] if isinstance(outputs, (list, tuple)) else outputs
    out = np.squeeze(np.asarray(out, dtype=np.float32))
    empty = (np.zeros((0, 4), np.float32), np.zeros(0, np.float32), np.zeros(0, np.int32))
    if out.ndim != 2:
        return empty
    if out.shape[0] < out.shape[1]:
        out = out.T  # -> (N, 4+nc)
    if out.shape[1] < 5:
        return empty
    cls = out[:, 4:]
    ids = cls.argmax(axis=1).astype(np.int32)
    conf = cls.max(axis=1)
    m = conf >= conf_thres
    if not np.any(m):
        return empty
    cx, cy, w, h = out[m, 0], out[m, 1], out[m, 2], out[m, 3]
    boxes = np.stack([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], axis=1)
    return boxes, conf[m], ids[m]


def nms_per_class(boxes, scores, ids, iou_thres, max_det=100):
    """Class-aware NMS: shift each class far apart, then plain NMS."""
    if len(scores) == 0:
        return []
    b = boxes + (ids.astype(np.float32) * 10000.0)[:, None]
    order = scores.argsort()[::-1]
    keep = []
    while order.size and len(keep) < max_det:
        i = order[0]
        keep.append(int(i))
        rest = order[1:]
        if rest.size == 0:
            break
        x1 = np.maximum(b[rest, 0], b[i, 0])
        y1 = np.maximum(b[rest, 1], b[i, 1])
        x2 = np.minimum(b[rest, 2], b[i, 2])
        y2 = np.minimum(b[rest, 3], b[i, 3])
        inter = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
        a_i = (b[i, 2] - b[i, 0]) * (b[i, 3] - b[i, 1])
        a_r = (b[rest, 2] - b[rest, 0]) * (b[rest, 3] - b[rest, 1])
        iou = inter / (a_i + a_r - inter + 1e-6)
        order = rest[iou <= iou_thres]
    return keep


def _param(name, default, alias=None):
    if rospy.has_param('~' + name):
        return rospy.get_param('~' + name)
    if alias and rospy.has_param('~' + alias):
        return rospy.get_param('~' + alias)
    return default


# ---------------------------------------------------------------- node
class FireDetector:
    def __init__(self):
        rospy.init_node('fire_detector')
        self.model_path = _param('model_path', os.path.expanduser('~/airael/models/fire-rgb-rk3588.rknn'))
        self.input_topic = _param('input_topic', '/main_camera/image_raw')
        self.det_topic = _param('detections_topic', '/fire/detections')
        self.ann_topic = _param('annotated_topic', '/fire/annotated')
        self.size = int(_param('input_size', 320))
        self.conf = float(_param('conf_thres', 0.5, 'conf_thresh'))
        self.iou = float(_param('iou_thres', 0.45, 'iou_thresh'))
        self.use_letterbox = bool(_param('letterbox', True))
        self.minmax = bool(_param('minmax_norm', False))
        self.use_rgb = bool(_param('use_rgb', True))
        self.names = [str(x) for x in (_param('class_names', ['campfire', 'tree']) or [])]
        npu_core = str(_param('npu_core', 'auto')).lower()

        log.info('model=%s input=%s size=%d conf=%.2f iou=%.2f letterbox=%s minmax=%s classes=%s',
                 self.model_path, self.input_topic, self.size, self.conf, self.iou,
                 self.use_letterbox, self.minmax, self.names)

        self.rk = RKNNLite()
        if self.rk.load_rknn(self.model_path) != 0:
            raise RuntimeError('load_rknn failed: %s' % self.model_path)
        cores = {
            'auto': getattr(RKNNLite, 'NPU_CORE_AUTO', None),
            '0': getattr(RKNNLite, 'NPU_CORE_0', None),
            '1': getattr(RKNNLite, 'NPU_CORE_1', None),
            '2': getattr(RKNNLite, 'NPU_CORE_2', None),
            '0_1_2': getattr(RKNNLite, 'NPU_CORE_0_1_2', None),
        }
        mask = cores.get(npu_core)
        ret = self.rk.init_runtime(core_mask=mask) if mask is not None else self.rk.init_runtime()
        if ret != 0:
            raise RuntimeError('init_runtime failed')

        self.bridge = CvBridge()
        self.pub_det = rospy.Publisher(self.det_topic, String, queue_size=10)
        self.pub_ann = rospy.Publisher(self.ann_topic, Image, queue_size=1)
        self.seq = 0
        self._shapes_logged = False
        self._fps_t, self._fps_n = time.time(), 0
        rospy.Subscriber(self.input_topic, Image, self.cb, queue_size=1, buff_size=2 ** 22)
        log.info('ready: %s -> %s', self.input_topic, self.det_topic)

    def cb(self, msg):
        t0 = time.time()
        try:
            frame = self.bridge.imgmsg_to_cv2(msg, desired_encoding='bgr8')
        except Exception as e:  # noqa: BLE001
            log.warning('cv_bridge: %s', e)
            return
        src = cv2.normalize(frame, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U) if self.minmax else frame
        h, w = src.shape[:2]

        if self.use_letterbox:
            inp, r, px, py = letterbox(src, self.size)
        else:
            inp = cv2.resize(src, (self.size, self.size), interpolation=cv2.INTER_LINEAR)
        if self.use_rgb:
            inp = cv2.cvtColor(inp, cv2.COLOR_BGR2RGB)

        try:
            outs = self.rk.inference(inputs=[np.expand_dims(inp, 0)])
        except Exception as e:  # noqa: BLE001
            log.error('inference: %s', e)
            return
        if not self._shapes_logged:
            shapes = [tuple(np.asarray(o).shape) for o in (outs if isinstance(outs, (list, tuple)) else [outs])]
            log.info('model outputs: %s (expected one tensor of shape (1, 4+%d, N))', shapes, len(self.names))
            self._shapes_logged = True

        boxes, scores, ids = decode(outs, self.conf)
        dets = []
        for i in nms_per_class(boxes, scores, ids, self.iou):
            x1, y1, x2, y2 = boxes[i]
            if self.use_letterbox:
                x1, x2 = (x1 - px) / r, (x2 - px) / r
                y1, y2 = (y1 - py) / r, (y2 - py) / r
            else:
                sx, sy = w / float(self.size), h / float(self.size)
                x1, x2, y1, y2 = x1 * sx, x2 * sx, y1 * sy, y2 * sy
            x1, x2 = float(np.clip(x1, 0, w - 1)), float(np.clip(x2, 0, w - 1))
            y1, y2 = float(np.clip(y1, 0, h - 1)), float(np.clip(y2, 0, h - 1))
            cid = int(ids[i])
            dets.append({
                'class_id': cid,
                'class_name': self.names[cid] if cid < len(self.names) else 'class_%d' % cid,
                'score': round(float(scores[i]), 4),
                'bbox': [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                'center': [round((x1 + x2) / 2, 1), round((y1 + y2) / 2, 1)],
            })

        self.seq += 1
        payload = {
            'stamp': msg.header.stamp.to_sec(),
            'seq': self.seq,
            'width': w,
            'height': h,
            'proc_ms': round((time.time() - t0) * 1000.0, 1),
            'detections': dets,
        }
        self.pub_det.publish(String(data=json.dumps(payload)))

        if self.pub_ann.get_num_connections() > 0:
            vis = frame.copy()
            for d in dets:
                x1, y1, x2, y2 = [int(v) for v in d['bbox']]
                cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 255, 0), 1)
                cv2.putText(vis, '%s %.2f' % (d['class_name'], d['score']), (x1, max(10, y1 - 3)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 0), 1, cv2.LINE_AA)
            out = self.bridge.cv2_to_imgmsg(vis, encoding='bgr8')
            out.header = msg.header
            self.pub_ann.publish(out)

        self._fps_n += 1
        now = time.time()
        if now - self._fps_t >= 5.0:
            log.info('FPS %.1f  last proc %.1f ms  dets %d',
                     self._fps_n / (now - self._fps_t), payload['proc_ms'], len(dets))
            self._fps_t, self._fps_n = now, 0

    def shutdown(self):
        try:
            self.rk.release()
        except Exception:  # noqa: BLE001
            pass


def main():
    node = None
    try:
        node = FireDetector()
        rospy.spin()
    except rospy.ROSInterruptException:
        pass
    finally:
        if node is not None:
            node.shutdown()


if __name__ == '__main__':
    main()
