"""Repository checks: scripts parse, the installer works, settings agree across files, and every
link and file path in the Markdown docs exists (the experts check for broken links)."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from rosstubs import REPO

BASH = shutil.which('bash')
NODE = shutil.which('node')


def read(rel):
    with open(os.path.join(REPO, rel), encoding='utf-8') as f:
        return f.read()


def md_files():
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.endswith('.md'):
                yield os.path.join(root, f)


class ScriptTests(unittest.TestCase):
    @unittest.skipUnless(BASH, 'bash not available')
    def test_shell_scripts_parse(self):
        for rel in ('drone/airael.sh', 'drone/install_drone.sh', 'training/train_gpu.sh'):
            r = subprocess.run([BASH, '-n', os.path.join(REPO, rel)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, rel + ': ' + r.stderr)

    @unittest.skipUnless(BASH, 'bash not available')
    def test_airael_without_arguments_prints_usage(self):
        home = tempfile.mkdtemp()
        try:
            r = subprocess.run([BASH, os.path.join(REPO, 'drone/airael.sh')], capture_output=True, text=True,
                               env=dict(os.environ, HOME=home))
            self.assertEqual(r.returncode, 1)
            self.assertIn('airael.sh start --detector', r.stdout)
            self.assertIn('airael.sh uninstall', r.stdout)
        finally:
            shutil.rmtree(home)

    @unittest.skipUnless(BASH, 'bash not available')
    def test_installer_copies_every_file(self):
        tmp = tempfile.mkdtemp()
        try:
            env = dict(os.environ, HOME=tmp, AIRAEL_DIR=os.path.join(tmp, 'airael'), GS_DIR=os.path.join(tmp, 'gs'),
                       YOLO_FACE_DIR=os.path.join(tmp, 'yolo_face'))
            os.makedirs(env['YOLO_FACE_DIR'])
            r = subprocess.run([BASH, os.path.join(REPO, 'drone/install_drone.sh')], capture_output=True, text=True, env=env)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            for rel in ('airael/airael.sh', 'airael/fire_geoloc.py', 'airael/dataset_server.py', 'airael/flight_report.py',
                        'gs/index.html', 'yolo_face/scripts/fire_detector_node.py', 'yolo_face/launch/fire_detector.launch'):
                self.assertTrue(os.path.isfile(os.path.join(tmp, rel)), rel)
            self.assertTrue(os.access(os.path.join(tmp, 'airael/airael.sh'), os.X_OK))
            r = subprocess.run([BASH, os.path.join(REPO, 'drone/install_drone.sh'), '--check'], capture_output=True, text=True, env=env)
            self.assertNotIn('differs', r.stdout)
        finally:
            shutil.rmtree(tmp)

    @unittest.skipUnless(NODE, 'node.js not available')
    def test_ground_station_javascript_parses(self):
        html = read('ground_station/index.html')
        js = re.search(r'<script>(.*)</script>', html, re.S).group(1)
        tmp = tempfile.NamedTemporaryFile('w', suffix='.js', delete=False)
        try:
            tmp.write(js)
            tmp.close()
            r = subprocess.run([NODE, '--check', tmp.name], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
        finally:
            os.unlink(tmp.name)

    def test_python_files_compile(self):
        for root, _, files in os.walk(REPO):
            for f in files:
                if f.endswith('.py'):
                    p = os.path.join(root, f)
                    compile(read(os.path.relpath(p, REPO)), p, 'exec')


class ConsistencyTests(unittest.TestCase):
    """The class list, camera, model path, size and ports must be the same everywhere."""

    def test_launch_defaults(self):
        args = {a.get('name'): a.get('default') for a in ET.fromstring(read('drone/fire_detector.launch')).iter('arg')}
        self.assertEqual(args['classes'], '[campfire, tree]')
        self.assertEqual(args['input'], '/main_camera/image_raw')
        self.assertEqual(args['size'], '320')
        self.assertTrue(args['model'].endswith('/airael/models/fire-rgb-rk3588.rknn'))

    def test_airael_defaults(self):
        sh = read('drone/airael.sh')
        self.assertIn('CLASSES="${CLASSES:-[campfire, tree]}"', sh)
        self.assertIn('DET_INPUT="${DET_INPUT:-/main_camera/image_raw}"', sh)
        self.assertIn('MODEL="${MODEL:-$HOME/airael/models/fire-rgb-rk3588.rknn}"', sh)
        self.assertIn('GS_PORT="${GS_PORT:-8020}"', sh)
        self.assertIn('DATASET_PY="${DATASET_PY:-$HOME/airael/dataset_server.py}"', sh)

    def test_tools_defaults(self):
        self.assertIn("DEFAULT_CLASSES = 'campfire,tree'", read('training/yolo_prep.py'))
        self.assertIn("ap.add_argument('--fire', default='campfire'", read('drone/flight_report.py'))
        gs = read('ground_station/index.html')
        self.assertIn('rosbridgePort: 9090', gs)
        self.assertIn('CFG.gsPort = 8020', gs)
        self.assertIn("passTol: 0.30", gs)


class DocsTests(unittest.TestCase):
    LINK = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
    # repository paths written in backticks, e.g. `drone/airael.sh` or `docs/module_B/test_plan.md`
    PATH = re.compile(r'`((?:drone|training|tools|tests|ground_station|docs|evidence)/[A-Za-z0-9_./-]+)`')

    def test_markdown_links_resolve(self):
        missing = []
        for md in md_files():
            for target in self.LINK.findall(open(md, encoding='utf-8').read()):
                if re.match(r'(https?:|mailto:|#)', target):
                    continue
                path = os.path.normpath(os.path.join(os.path.dirname(md), target.split('#')[0]))
                if not os.path.exists(path):
                    missing.append('%s -> %s' % (os.path.relpath(md, REPO), target))
        self.assertEqual(missing, [])

    def test_repository_paths_in_docs_exist(self):
        missing = []
        for md in md_files():
            for p in self.PATH.findall(open(md, encoding='utf-8').read()):
                if not os.path.exists(os.path.join(REPO, p.rstrip('/'))):
                    missing.append('%s: %s' % (os.path.relpath(md, REPO), p))
        self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main()
