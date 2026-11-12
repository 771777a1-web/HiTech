"""Module B analysis (drone/flight_report.py): FPS share (MC4), event completeness (MC6 log fields),
position error against tape-measured truth (MC5). No ROS needed for these functions."""
import unittest

import rosstubs


class FlightReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f = rosstubs.load('drone/flight_report.py', 'flight_report')

    def test_fps_share_counts_whole_seconds_after_skip(self):
        stamps = [i / 30.0 for i in range(30 * 20)]            # 20 s at 30 FPS
        r = self.f.fps_share(stamps, skip_s=5.0, fps_min=10)
        self.assertEqual(r['seconds'], 14)
        self.assertEqual(r['share_pct'], 100.0)
        self.assertGreaterEqual(r['min_fps'], 29)

    def test_fps_share_gap_counts_as_zero(self):
        stamps = [i / 20.0 for i in range(20 * 10)] + [15 + i / 20.0 for i in range(20 * 5)]
        r = self.f.fps_share(stamps, skip_s=0.0, fps_min=10)
        self.assertEqual(r['min_fps'], 0)
        self.assertLess(r['share_pct'], 90)

    def test_fps_share_needs_frames(self):
        self.assertIsNone(self.f.fps_share([1.0]))
        self.assertIsNone(self.f.fps_share([1.0, 2.0], skip_s=5.0))

    def test_event_completeness(self):
        good = {'stamp': 1.0, 'x': 0.1, 'y': 0.2, 'class_name': 'campfire', 'score': 0.9}
        bad = dict(good, x=float('nan'))
        r = self.f.event_completeness([good, bad, dict(good, class_name='')])
        self.assertEqual((r['events'], r['complete'], r['pct']), (3, 1, 33.3))
        self.assertIsNone(self.f.event_completeness([])['pct'])

    def test_position_errors_match_by_class(self):
        objs = [{'class_name': 'campfire', 'x': 1.3, 'y': 0.75, 'id': 1}, {'class_name': 'tree', 'x': 0, 'y': 0, 'id': 2},
                {'class_name': 'campfire', 'x': 3.0, 'y': 3.0, 'id': 3}]
        errs, extra = self.f.position_errors(objs, [('campfire', 1.5, 0.75), ('tree', 0.3, 0.4)])
        self.assertEqual(errs[0]['error_m'], 0.2)
        self.assertEqual(errs[1]['error_m'], 0.5)
        self.assertEqual([o['id'] for o in extra], [3])
        errs, _ = self.f.position_errors([], [('campfire', 0, 0)])
        self.assertFalse(errs[0]['found'])

    def test_parse_truth(self):
        self.assertEqual(self.f.parse_truth(['campfire=1.5,0.75', 'tree=-0.75,1.5']),
                         [('campfire', 1.5, 0.75), ('tree', -0.75, 1.5)])
        with self.assertRaises(SystemExit):
            self.f.parse_truth(['campfire:1,2'])


if __name__ == '__main__':
    unittest.main()
