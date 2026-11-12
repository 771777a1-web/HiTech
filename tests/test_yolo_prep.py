"""Dataset tool (training/yolo_prep.py): split by session, negatives, bad labels, Roboflow import."""
import contextlib
import io
import os
import shutil
import tempfile
import unittest

from PIL import Image

import rosstubs


def png(path, size=(64, 48)):
    Image.new('RGB', size).save(path)


def write(path, text):
    with open(path, 'w') as f:
        f.write(text)


def read(path):
    with open(path) as f:
        return f.read()


class YoloPrepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.y = rosstubs.load('training/yolo_prep.py', 'yolo_prep')

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.y.main(list(args))
        return out.getvalue()

    def test_build_splits_by_session_and_handles_negatives(self):
        imgs, labs, ds = (os.path.join(self.tmp, d) for d in ('img', 'lab', 'ds'))
        os.makedirs(imgs); os.makedirs(labs)
        for sess, n in (('bonfire_20261111_202106', 3), ('test_bonfire_20261111_203000', 2), ('background_20261111_202531', 2)):
            for i in range(n):
                png(os.path.join(imgs, '%s__%d.png' % (sess, i)))
        for i in range(3):
            write(os.path.join(labs, 'bonfire_20261111_202106__%d.txt' % i), '0 0.5 0.5 0.2 0.2\n1 0.1 0.1 0.1 0.1\n')
        write(os.path.join(labs, 'test_bonfire_20261111_203000__0.txt'), '0 0.5 0.5 0.2 0.2\n5 0.5 0.5 0.1 0.1\n')
        # test_bonfire_..__1 has no label and is not a negative session: skipped
        out = self.run_main('build', '--images', imgs, '--labels', labs, '--out', ds)
        self.assertEqual(len(os.listdir(os.path.join(ds, 'images', 'val'))), 1)
        self.assertEqual(len(os.listdir(os.path.join(ds, 'images', 'train'))), 5)     # 3 labelled + 2 negatives
        self.assertIn('2 negative-session images used as empty, 1 images skipped', out)
        self.assertIn('1 bad label lines', out)                                            # class 5 does not exist
        yaml = read(os.path.join(ds, 'data.yaml'))
        self.assertIn('  0: campfire\n  1: tree\n', yaml)

    def test_rfimport_renumbers_by_name_and_drops_unknown_classes(self):
        rf = os.path.join(self.tmp, 'rf')
        for split in ('train', 'valid'):
            os.makedirs(os.path.join(rf, split, 'images')); os.makedirs(os.path.join(rf, split, 'labels'))
        write(os.path.join(rf, 'data.yaml'), "names: ['tree', 'campfire', 'uae flag with stand']\n")
        png(os.path.join(rf, 'train', 'images', 'bonfire_1__100_png.rf.abc123.jpg'), (640, 480))
        write(os.path.join(rf, 'train', 'labels', 'bonfire_1__100_png.rf.abc123.txt'),
            '1 0.5 0.5 0.2 0.2\n0 0.3 0.3 0.1 0.1\n2 0.7 0.7 0.1 0.1\n')
        out_imgs, labs = os.path.join(self.tmp, 'imgs'), os.path.join(self.tmp, 'labs')
        out = self.run_main('rfimport', '--zip', rf, '--out-images', out_imgs, '--labels', labs)
        self.assertIn('RGB camera size', out)
        self.assertEqual(read(os.path.join(labs, 'bonfire_1__100.txt')),
                         '0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1\n')                          # campfire=0, tree=1, flag dropped
        self.assertTrue(os.path.exists(os.path.join(out_imgs, 'bonfire_1__100.jpg')))
        self.assertIn('bonfire_1__100.jpg', read(os.path.join(out_imgs, 'manifest.csv')))

    def test_collect_crops_old_stacked_thermal_frames(self):
        src, out = os.path.join(self.tmp, 'dataset'), os.path.join(self.tmp, 'to_label')
        os.makedirs(os.path.join(src, 'bonfire_20261110_100000', 'thermal'))
        png(os.path.join(src, 'bonfire_20261110_100000', 'thermal', '1.png'), (256, 384))
        res = self.run_main('collect', '--src', src, '--out', out)
        self.assertIn('cropped to 256x192', res)
        with Image.open(os.path.join(out, 'bonfire_20261110_100000__1.png')) as im:
            self.assertEqual(im.size, (256, 192))


if __name__ == '__main__':
    unittest.main()
