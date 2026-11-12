"""Geolocation (drone/fire_geoloc.py): pixel -> ray -> floor plane, object tracking, and the node's
event output with a stand-in tf tree. This is the team's own localisation algorithm."""
import json
import math
import time
import unittest

import numpy as np

import rosstubs

DOWN = (1.0, 0.0, 0.0, 0.0)   # optical frame rotated 180 deg about x: camera z (forward) points at the floor


class GeometryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = rosstubs.load('drone/fire_geoloc.py', 'fire_geoloc')
        cls.K = np.array([[300., 0, 320], [0, 300., 240], [0, 0, 1]])

    def test_quaternion_identity(self):
        np.testing.assert_allclose(self.g.quat_to_mat(0, 0, 0, 1), np.eye(3))

    def test_centre_pixel_lands_under_the_camera(self):
        R, o = self.g.quat_to_mat(*DOWN), np.array([1.0, -0.5, 1.5])
        p = self.g.ray_to_plane(o, R, self.g.pixel_to_ray(320, 240, self.K), 0.15)
        np.testing.assert_allclose(p, [1.0, -0.5, 0.15], atol=1e-9)

    def test_pixel_offset_scales_with_height(self):
        R, o = self.g.quat_to_mat(*DOWN), np.array([0.0, 0.0, 1.5])
        p = self.g.ray_to_plane(o, R, self.g.pixel_to_ray(380, 240, self.K), 0.15)
        # 60 px right at f = 300 px is 0.2 rad-ish slope; 1.35 m below the camera -> 0.27 m
        self.assertAlmostEqual(p[0], 0.27, places=6)
        self.assertAlmostEqual(p[1], 0.0, places=9)

    def test_ray_that_does_not_point_down_is_rejected(self):
        R, o = np.eye(3), np.array([0.0, 0.0, 1.5])      # camera looking up
        self.assertIsNone(self.g.ray_to_plane(o, R, self.g.pixel_to_ray(320, 240, self.K), 0.15))

    def test_camera_below_the_object_plane_is_rejected(self):
        R, o = self.g.quat_to_mat(*DOWN), np.array([0.0, 0.0, 0.08])   # drone resting on the floor
        self.assertIsNone(self.g.ray_to_plane(o, R, self.g.pixel_to_ray(320, 240, self.K), 0.15))

    def test_zero_distortion_keeps_the_pinhole_ray(self):
        a = self.g.pixel_to_ray(400, 100, self.K, [0, 0, 0, 0, 0])
        b = self.g.pixel_to_ray(400, 100, self.K)
        np.testing.assert_allclose(a, b)


class TrackerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = rosstubs.load('drone/fire_geoloc.py', 'fire_geoloc')

    def test_two_sightings_confirm_one_object(self):
        t = self.g.Tracker()
        self.assertEqual(t.add('campfire', 1.0, 1.0, 0.8, 0, now=0.0)[0], None)
        kind, o = t.add('campfire', 1.1, 1.0, 0.9, 0, now=0.1)
        self.assertEqual((kind, o['id'], o['hits']), ('new', 1, 2))
        self.assertAlmostEqual(o['score'], 0.9)

    def test_far_sightings_and_other_classes_stay_apart(self):
        t = self.g.Tracker(merge_radius=0.6)
        for now in (0.0, 0.1):
            t.add('campfire', 0.0, 0.0, 0.9, 0, now)
            t.add('campfire', 2.0, 0.0, 0.9, 0, now)
            t.add('tree', 0.1, 0.0, 0.9, 0, now)
        self.assertEqual(len(t.confirmed()), 3)

    def test_single_frame_false_alarm_is_not_reported(self):
        t = self.g.Tracker()
        t.add('campfire', 0.0, 0.0, 0.9, 0, now=0.0)
        t.add('campfire', 0.0, 0.0, 0.9, 0, now=5.0)      # second sighting too late: candidate restarts
        self.assertEqual(t.confirmed(), [])

    def test_update_after_period_uses_median(self):
        t = self.g.Tracker(update_period=2.0)
        t.add('campfire', 0.0, 0.0, 0.9, 0, now=0.0)
        t.add('campfire', 0.2, 0.0, 0.9, 0, now=0.1)
        self.assertEqual(t.add('campfire', 0.1, 0.0, 0.9, 0, now=1.0)[0], None)
        kind, o = t.add('campfire', 0.5, 0.0, 0.9, 0, now=2.2)
        self.assertEqual(kind, 'update')
        self.assertAlmostEqual(o['x'], 0.15)                # median of 0, 0.2, 0.1, 0.5
        self.assertAlmostEqual(t.spread(o), 0.35)


class NodeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.g = rosstubs.load('drone/fire_geoloc.py', 'fire_geoloc')

    def setUp(self):
        rosstubs.PARAMS.clear()
        rosstubs.PUBLISHED.clear()
        rosstubs.TF.clear()
        self.node = self.g.GeoLoc()
        # camera_info at 1280x960 while the detector image is 640x480: K must be scaled by 0.5
        self.node.ci_cb(rosstubs.Msg(K=[600., 0, 640, 0, 600., 480, 0, 0, 1], D=[0, 0, 0, 0, 0], distortion_model='plumb_bob',
                                     width=1280, height=960, header=rosstubs.Msg(frame_id='main_camera_optical')))

    def det(self, cls, u, v, score=0.9):
        return rosstubs.Msg(data=json.dumps({'stamp': time.time(), 'width': 640, 'height': 480, 'detections': [
            {'class_name': cls, 'score': score, 'bbox': [u - 10, v - 10, u + 10, v + 10], 'center': [u, v]}]}))

    def events(self):
        return [json.loads(d) for t, d in rosstubs.PUBLISHED if t == '/fire/events']

    def test_campfire_event_has_every_logged_field(self):
        rosstubs.TF[('aruco_map', 'main_camera_optical')] = rosstubs.transform(1.0, -0.5, 1.5, *DOWN)
        self.node.det_cb(self.det('campfire', 380, 240))
        self.node.det_cb(self.det('campfire', 380, 240))
        evs = self.events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        for k in ('stamp', 'class_name', 'score', 'x', 'y', 'id', 'kind'):
            self.assertIn(k, e)
        self.assertEqual((e['class_name'], e['kind'], e['id']), ('campfire', 'new', 1))
        self.assertAlmostEqual(e['x'], 1.0 + 60 / 300.0 * 1.35, places=3)
        self.assertAlmostEqual(e['y'], -0.5, places=3)

    def test_low_score_is_ignored(self):
        rosstubs.TF[('aruco_map', 'main_camera_optical')] = rosstubs.transform(0, 0, 1.5, *DOWN)
        for _ in range(3):
            self.node.det_cb(self.det('campfire', 320, 240, score=0.3))
        self.assertEqual(self.events(), [])

    def test_without_marker_pose_nothing_is_reported(self):
        for _ in range(3):
            self.node.det_cb(self.det('campfire', 320, 240))
        self.assertEqual(self.events(), [])
        self.assertGreater(self.node.stats['tf_fail'], 0)

    def test_last_marker_fix_is_used_when_markers_drop_out(self):
        link = rosstubs.transform(0.5, 0.0, 0.0, 0, 0, 0, 1)                # aruco_map <- map: 0.5 m shift
        rosstubs.TF[('aruco_map', 'map')] = link
        self.node.det_cb(self.det('campfire', 320, 240))                    # learns the link, no direct pose
        del rosstubs.TF[('aruco_map', 'map')]
        rosstubs.TF[('map', 'main_camera_optical')] = rosstubs.transform(1.0, 1.0, 1.5, *DOWN)
        self.node.det_cb(self.det('campfire', 320, 240))
        self.node.det_cb(self.det('campfire', 320, 240))
        e = self.events()[0]
        self.assertAlmostEqual(e['x'], 1.5, places=3)
        self.assertAlmostEqual(e['y'], 1.0, places=3)
        self.assertTrue(math.isfinite(e['cam_z']))


if __name__ == '__main__':
    unittest.main()
