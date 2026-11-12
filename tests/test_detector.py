"""Detector maths (drone/fire_detector_node.py): YOLOv8 output decoding, class-aware NMS, letterbox,
and one full frame through the node with a stand-in NPU."""
import json
import unittest

import numpy as np

try:
    import cv2  # noqa: F401  the node needs OpenCV for resizing
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False

import rosstubs


def yolo_output(boxes, nc=2, n=2100):
    """Fake YOLOv8 head (1, 4+nc, n): boxes = [(cx, cy, w, h, class_id, score), ...] in 320-px input space."""
    out = np.zeros((1, 4 + nc, n), np.float32)
    for i, (cx, cy, w, h, c, s) in enumerate(boxes):
        out[0, :4, i] = (cx, cy, w, h)
        out[0, 4 + c, i] = s
    return [out]


@unittest.skipUnless(HAVE_CV2, 'OpenCV not installed')
class DetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = rosstubs.load('drone/fire_detector_node.py', 'fire_detector_node')

    def test_decode_keeps_boxes_above_threshold(self):
        outs = yolo_output([(160, 160, 40, 20, 0, 0.9), (50, 50, 10, 10, 1, 0.3)])
        boxes, scores, ids = self.m.decode(outs, 0.5)
        self.assertEqual(len(scores), 1)
        np.testing.assert_allclose(boxes[0], [140, 150, 180, 170])
        self.assertEqual(int(ids[0]), 0)
        self.assertAlmostEqual(float(scores[0]), 0.9, places=5)

    def test_decode_empty_and_bad_shapes(self):
        self.assertEqual(len(self.m.decode(yolo_output([]), 0.5)[1]), 0)
        self.assertEqual(len(self.m.decode([np.zeros((1, 2, 3, 4))], 0.5)[1]), 0)

    def test_nms_is_per_class(self):
        boxes = np.array([[0, 0, 10, 10], [1, 1, 11, 11], [0, 0, 10, 10]], np.float32)
        scores = np.array([0.9, 0.8, 0.7], np.float32)
        ids = np.array([0, 0, 1], np.int32)
        keep = self.m.nms_per_class(boxes, scores, ids, 0.45)
        self.assertEqual(sorted(keep), [0, 2])   # same-class overlap removed, other class kept

    def test_letterbox_640x480(self):
        img = np.zeros((480, 640, 3), np.uint8)
        canvas, r, px, py = self.m.letterbox(img, 320)
        self.assertEqual(canvas.shape, (320, 320, 3))
        self.assertAlmostEqual(r, 0.5)
        self.assertEqual((px, py), (0, 40))

    def test_one_frame_through_the_node(self):
        rosstubs.PARAMS.clear()
        rosstubs.PUBLISHED.clear()
        rosstubs.PARAMS.update({'~class_names': ['campfire', 'tree'], '~input_size': 320})
        node = self.m.FireDetector()
        # a campfire at input (160, 140) size 40x20 -> original image: x = 160/0.5, y = (140-40)/0.5
        rosstubs.RKNNLite.OUTPUT = yolo_output([(160, 140, 40, 20, 0, 0.92)])
        msg = rosstubs.Msg(img=np.zeros((480, 640, 3), np.uint8),
                           header=rosstubs.Msg(stamp=rosstubs._Time(1794464345.5)))
        node.cb(msg)
        topic, data = rosstubs.PUBLISHED[-1]
        self.assertEqual(topic, '/fire/detections')
        d = json.loads(data)
        self.assertEqual((d['width'], d['height'], d['seq']), (640, 480, 1))
        self.assertEqual(len(d['detections']), 1)
        det = d['detections'][0]
        self.assertEqual(det['class_name'], 'campfire')
        self.assertEqual(det['bbox'], [280.0, 180.0, 360.0, 220.0])
        self.assertEqual(det['center'], [320.0, 200.0])
        self.assertEqual(rosstubs.RKNNLite.LAST_INPUT.shape, (1, 320, 320, 3))

    def test_node_defaults_match_the_deployed_model(self):
        rosstubs.PARAMS.clear()
        node = self.m.FireDetector()
        self.assertEqual(node.names, ['campfire', 'tree'])
        self.assertEqual(node.input_topic, '/main_camera/image_raw')
        self.assertEqual((node.size, node.conf, node.iou), (320, 0.5, 0.45))


if __name__ == '__main__':
    unittest.main()
