#!/usr/bin/env python3
"""Airael YOLO dataset helper (runs on the laptop).

Step A, gather the thermal (or --sub rgb) frames of all sessions into one folder for labelling:
  python yolo_prep.py collect --src ~/dataset --out ~/yolo/to_label [--every 2] [--max 300]
    * one flat folder, files named <session>__<frame>.png (so labels can be traced back)
    * frames from the old stacked 256x384 mode are cropped to the top 192 rows
    * adds to ~/yolo/to_label/manifest.csv (file, session, label, altitude), so several
      collect runs with different --only/--every settings can fill the same folder

Step B, after labelling (YOLO txt files, one per image, same base name):
  python yolo_prep.py build --images ~/yolo/to_label --labels ~/yolo/labels \
         --classes campfire,tree --out ~/yolo/ds
    * split by SESSION, never by frame (neighbouring frames are near copies)
    * sessions whose name starts with test_ go to val; if there are none,
      about 20 % of the sessions of each label go to val
    * images without a label file are skipped, except in negative sessions
      (name starts with one of --neg, e.g. background, flag, drone), which get an
      empty label (= "nothing to detect here"). If you DID box a tree or campfire
      in a negative-session image, its label file is used as usual.
    * writes ~/yolo/ds/data.yaml and prints boxes per class per split
Step B' (labels made in Roboflow instead): bring a Roboflow "YOLOv8" export back to our image names:
  python yolo_prep.py rfimport --zip ~/Downloads/<export>.zip --images ~/yolo/to_label --labels ~/yolo/labels \
         --classes campfire,tree
    * maps Roboflow names (<name>_png.rf.<hash>.jpg) back to <name>.png in --images
    * re-numbers classes by NAME, so Roboflow's class order does not matter
    * refuses augmented copies (same image twice with different boxes): export without augmentation
    * then run "build" as usual, which splits by session (Roboflow's own split is by random image)
    * --out-images DIR: also copy the export's own images to DIR (as <name>.jpg, with manifest.csv) and use
      them for build. Use this when the labelled images are not the ones in ~/yolo/to_label, e.g. RGB frames
      (thermal and RGB frames share names, so matching RGB labels to thermal images would be wrong).

The deployed model was built with:
  python yolo_prep.py rfimport --zip "<Roboflow export folder>" --out-images ~/yolo/rgb_img --labels ~/yolo/rgb_labels --classes campfire,tree
  python yolo_prep.py build --images ~/yolo/rgb_img --labels ~/yolo/rgb_labels --classes campfire,tree --out ~/yolo/ds_rgb
"""

import argparse
import csv
import os
import random
import shutil
import sys
from collections import defaultdict

try:
    from PIL import Image
except ImportError:
    sys.exit('Pillow is needed: pip install pillow (it comes with ultralytics)')

DEFAULT_NEG = 'background,test_background,flag,red_flag,red_tape,red_tapeflag,tape_red,drone,remote'
DEFAULT_CLASSES = 'campfire,tree'


def expand(p):
    return os.path.abspath(os.path.expanduser(p))


def session_label(sdir):
    """Label from meta.json (dataset_server) or index.csv, else the session name without the date."""
    import json
    import re
    try:
        with open(os.path.join(sdir, 'meta.json')) as f:
            lab = json.load(f).get('label')
            if lab:
                return lab
    except (OSError, ValueError):
        pass
    try:
        with open(os.path.join(sdir, 'index.csv')) as f:
            row = next(csv.DictReader(f), None)
            if row and row.get('label'):
                return row['label']
    except (OSError, StopIteration):
        pass
    name = os.path.basename(sdir.rstrip('/'))
    return re.sub(r'_?\d{8}_\d{6}$', '', name) or name


def read_alts(sdir):
    alts = {}
    try:
        with open(os.path.join(sdir, 'index.csv')) as f:
            for row in csv.DictReader(f):
                alts[os.path.basename(row.get('thermal_file', ''))] = row.get('alt_m', '')
    except OSError:
        pass
    return alts


def cmd_collect(a):
    src, out = expand(a.src), expand(a.out)
    os.makedirs(out, exist_ok=True)
    mpath = os.path.join(out, 'manifest.csv')
    manifest = {}
    if os.path.exists(mpath):   # keep rows from earlier collect runs
        with open(mpath) as f:
            for r in csv.DictReader(f):
                manifest[r['file']] = [r['file'], r['session'], r['label'], r.get('alt_m', '')]
    total, bad_total = 0, 0
    for sname in sorted(os.listdir(src)):
        sdir = os.path.join(src, sname)
        tdir = os.path.join(sdir, a.sub)
        if a.sub == 'thermal' and not os.path.isdir(tdir) and os.path.isdir(sdir) and any(f.endswith('.png') for f in os.listdir(sdir)):
            tdir = sdir   # old layout: PNGs directly in the folder (e.g. ~/dataset/thermal)
        if not os.path.isdir(tdir) or (a.only and not any(sname.startswith(p) for p in a.only.split(','))):
            continue
        if a.exclude and any(sname.startswith(p) for p in a.exclude.split(',')):
            continue
        files = sorted(f for f in os.listdir(tdir) if f.endswith('.png'))
        files = files[::max(1, a.every)]
        if a.max and len(files) > a.max:   # spread evenly over the session
            step = len(files) / float(a.max)
            files = [files[int(i * step)] for i in range(a.max)]
        if not files:
            continue
        label, alts, n, cropped, bad = session_label(sdir), read_alts(sdir), 0, 0, 0
        for f in files:
            dst = os.path.join(out, '%s__%s' % (sname, f))
            try:
                im = Image.open(os.path.join(tdir, f)); im.load()
            except Exception:   # truncated / empty PNG (e.g. written while copying)
                bad += 1
                continue
            if a.sub == 'thermal' and im.size == (256, 384):   # old stacked mode: top half is the image (defect D2)
                im = im.crop((0, 0, 256, 192))
                cropped += 1
            im.save(dst)
            manifest[os.path.basename(dst)] = [os.path.basename(dst), sname, label, alts.get(f, '')]
            n += 1
        total += n
        print('%-40s label %-18s %4d images%s%s' % (sname, label, n, ('  (%d cropped to 256x192)' % cropped) if cropped else '',
                                                   ('  (%d UNREADABLE skipped)' % bad) if bad else ''))
        bad_total += bad
    with open(mpath, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['file', 'session', 'label', 'alt_m'])
        w.writerows(sorted(manifest.values()))
    print('\n%d images added this run, %d in %s in total' % (total, len(manifest), out))
    if bad_total:
        print('%d unreadable PNGs skipped' % bad_total)


def is_negative(session, negs):
    s = session.lower()
    return any(s.startswith(p) for p in negs)


def cmd_build(a):
    imgs, labs, out = expand(a.images), expand(a.labels), expand(a.out)
    classes = [c.strip() for c in a.classes.split(',') if c.strip()]
    negs = [p.strip().lower() for p in a.neg.split(',') if p.strip()]
    nc = len(classes)
    man = {}
    mpath = os.path.join(imgs, 'manifest.csv')
    if os.path.exists(mpath):
        with open(mpath) as f:
            for r in csv.DictReader(f):
                man[r['file']] = (r['session'], r['label'])

    # images grouped by session
    by_sess = defaultdict(list)
    for f in sorted(os.listdir(imgs)):
        if f.lower().endswith(('.png', '.jpg', '.jpeg')):
            sess, lab = man.get(f, (f.split('__')[0], f.split('__')[0].split('_')[0]))
            by_sess[sess].append((f, lab))
    if not by_sess:
        sys.exit('no images in %s' % imgs)

    # split by session
    sessions = sorted(by_sess)
    val = {s for s in sessions if s.startswith(a.test_prefix)}
    if not val:
        rnd = random.Random(a.seed)
        per_label = defaultdict(list)
        for s in sessions:
            per_label[by_sess[s][0][1]].append(s)
        for lab, ss in sorted(per_label.items()):
            if len(ss) >= 2:
                k = max(1, int(round(len(ss) * a.val_frac)))
                val.update(rnd.sample(ss, k))
        if not val:
            print('WARNING: every label has only one session, so the split is by frame order inside each session '
                  '(last %d %%). Record separate test_ sessions for an honest mAP.' % int(a.val_frac * 100))

    for sub in ('images/train', 'images/val', 'labels/train', 'labels/val'):
        d = os.path.join(out, sub)
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)

    stats = {sp: {'images': 0, 'empty': 0, 'boxes': [0] * nc} for sp in ('train', 'val')}
    skipped, bad, neg_empty = 0, 0, 0
    for sess in sessions:
        items = by_sess[sess]
        for i, (f, lab) in enumerate(items):
            if val:
                split = 'val' if sess in val else 'train'
            else:   # fallback: tail of each session
                split = 'val' if i >= len(items) * (1 - a.val_frac) else 'train'
            stem = os.path.splitext(f)[0]
            lp = os.path.join(labs, stem + '.txt')
            lines = []
            if os.path.exists(lp):
                with open(lp) as fh:
                    for ln in fh:
                        p = ln.split()
                        if not p:
                            continue
                        try:
                            c = int(p[0]); x, y, w, h = map(float, p[1:5])
                        except (ValueError, IndexError):
                            bad += 1; continue
                        if not (0 <= c < nc) or not all(0 <= v <= 1 for v in (x, y, w, h)) or w <= 0 or h <= 0:
                            bad += 1; continue
                        lines.append('%d %.6f %.6f %.6f %.6f' % (c, x, y, w, h))
                        stats[split]['boxes'][c] += 1
            elif is_negative(sess, negs):
                neg_empty += 1
            else:
                skipped += 1
                continue
            shutil.copy2(os.path.join(imgs, f), os.path.join(out, 'images', split, f))
            with open(os.path.join(out, 'labels', split, stem + '.txt'), 'w') as fh:
                fh.write('\n'.join(lines) + ('\n' if lines else ''))
            stats[split]['images'] += 1
            stats[split]['empty'] += 0 if lines else 1

    with open(os.path.join(out, 'data.yaml'), 'w') as f:
        f.write('# Airael fire monitoring, built by yolo_prep.py (split by session)\n')
        f.write('path: %s\ntrain: images/train\nval: images/val\n' % out)
        f.write('names:\n' + ''.join('  %d: %s\n' % (i, c) for i, c in enumerate(classes)))

    print('val sessions (%d): %s' % (len(val), ', '.join(sorted(val)) or '(tail of each session)'))
    print('\n%-6s %7s %7s  %s' % ('split', 'images', 'empty', '  '.join('%s boxes' % c for c in classes)))
    for sp in ('train', 'val'):
        st = stats[sp]
        print('%-6s %7d %7d  %s' % (sp, st['images'], st['empty'], '  '.join('%*d' % (len(c) + 6, n) for c, n in zip(classes, st['boxes']))))
    print('\n%d negative-session images used as empty, %d images skipped (no label file, not negative), '
          '%d bad label lines' % (neg_empty, skipped, bad))
    for c, n in zip(classes, stats['val']['boxes']):
        if n == 0:
            print('WARNING: no "%s" boxes in val, so its mAP cannot be measured' % c)
    print('dataset ready: %s' % os.path.join(out, 'data.yaml'))


def _rf_names(text):
    """Class names from a Roboflow data.yaml (list or dict form), without needing PyYAML."""
    try:
        import yaml
        d = yaml.safe_load(text) or {}
        n = d.get('names')
        if isinstance(n, dict):
            return [str(n[k]) for k in sorted(n, key=int)]
        if isinstance(n, list):
            return [str(x) for x in n]
    except Exception:  # noqa: BLE001
        pass
    import re
    m = re.search(r"names:\s*\[(.*?)\]", text, re.S)
    if m:
        return [x.strip().strip('\'"') for x in m.group(1).split(',') if x.strip()]
    return re.findall(r"^\s*(?:\d+\s*:|-)\s*['\"]?([^'\"\n]+?)['\"]?\s*$", text.split('names:', 1)[-1], re.M)


def cmd_rfimport(a):
    import re
    import zipfile
    src, imgs, labs = expand(a.zip), expand(a.images), expand(a.labels)
    classes = [c.strip() for c in a.classes.split(',') if c.strip()]
    if os.path.isdir(src):
        files = {os.path.relpath(os.path.join(r, f), src): os.path.join(r, f) for r, _, fs in os.walk(src) for f in fs}
        read = lambda k: open(files[k], 'rb').read()   # noqa: E731
        names_in = list(files)
    else:
        z = zipfile.ZipFile(src)
        names_in = z.namelist()
        read = z.read
    yamls = [n for n in names_in if n.endswith('data.yaml')]
    if not yamls:
        sys.exit('no data.yaml in %s: export the dataset in "YOLOv8" format' % src)
    rf_names = _rf_names(read(yamls[0]).decode('utf-8', 'ignore'))
    print('Roboflow classes: %s' % rf_names)
    remap = {}
    for i, n in enumerate(rf_names):
        key = n.strip().lower()
        if key in [c.lower() for c in classes]:
            remap[i] = [c.lower() for c in classes].index(key)
        else:
            print('WARNING: Roboflow class "%s" is not in --classes %s: its boxes are dropped' % (n, classes))
    for c in classes:
        if c.lower() not in [n.strip().lower() for n in rf_names]:
            print('WARNING: class "%s" has no boxes in this export' % c)

    sample_img = next((n for n in names_in if re.search(r'/images/[^/]+\.(jpe?g|png)$', n, re.I)), None)
    if sample_img:
        try:
            import io
            sz = Image.open(io.BytesIO(read(sample_img))).size
            kind = {(256, 192): 'thermal camera size', (640, 480): 'RGB camera size: these are RGB frames, not thermal'}.get(
                tuple(sz), 'resized by Roboflow; fine for labels, because YOLO boxes are relative to the image')
            print('export image size: %dx%d  (%s)' % (sz[0], sz[1], kind))
        except Exception:  # noqa: BLE001
            pass

    out_imgs = expand(a.out_images) if a.out_images else None
    img_of = {}
    for n in names_in:
        m = re.search(r'/images/([^/]+)\.(jpe?g|png)$', n.replace('\\', '/'), re.I)
        if m:
            img_of[re.sub(r'_(png|jpe?g)\.rf\.[0-9a-zA-Z]+$', '', m.group(1))] = n
    by_orig = defaultdict(list)
    for n in names_in:
        if '/labels/' not in n.replace('\\', '/') or not n.endswith('.txt'):
            continue
        stem = os.path.splitext(os.path.basename(n))[0]
        orig = re.sub(r'_(png|jpe?g)\.rf\.[0-9a-zA-Z]+$', '', stem)
        lines = []
        for ln in read(n).decode('utf-8', 'ignore').splitlines():
            p = ln.split()
            if len(p) < 5:
                continue
            try:
                c = int(p[0])
            except ValueError:
                continue
            if c in remap:
                lines.append(' '.join([str(remap[c])] + p[1:5]))
        by_orig[orig].append('\n'.join(lines))

    os.makedirs(labs, exist_ok=True)
    if out_imgs:
        os.makedirs(out_imgs, exist_ok=True)
        have = set(img_of)
    else:
        have = {os.path.splitext(f)[0] for f in os.listdir(imgs)} if os.path.isdir(imgs) else set()
    man_rows = []
    written = boxes = conflicts = 0
    unmatched = []
    for orig, versions in sorted(by_orig.items()):
        if len(set(versions)) > 1:
            conflicts += 1
            continue
        if have and orig not in have:
            unmatched.append(orig)
            continue
        txt = versions[0]
        if out_imgs:
            ext = os.path.splitext(img_of[orig])[1].lower()
            with open(os.path.join(out_imgs, orig + ext), 'wb') as f:
                f.write(read(img_of[orig]))
            sess = orig.split('__')[0]
            man_rows.append([orig + ext, sess, re.sub(r'_?\d{8}_\d{6}$', '', sess) or sess, ''])
        with open(os.path.join(labs, orig + '.txt'), 'w') as f:
            f.write(txt + ('\n' if txt else ''))
        written += 1
        boxes += len(txt.splitlines()) if txt else 0
    if out_imgs:
        with open(os.path.join(out_imgs, 'manifest.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['file', 'session', 'label', 'alt_m'])
            w.writerows(sorted(man_rows))
        print('images copied to %s: %d' % (out_imgs, len(man_rows)))
    print('\nlabel files written to %s: %d (%d boxes)' % (labs, written, boxes))
    if conflicts:
        print('SKIPPED %d images that appear more than once with different boxes (Roboflow augmentation). '
              'Export a version WITHOUT augmentation to keep them.' % conflicts)
    if unmatched:
        print('%d labels have no image in %s, e.g. %s' % (len(unmatched), imgs, ', '.join(unmatched[:3])))
        print('  -> those images were not uploaded from ~/yolo/to_label. If none match, train on the Roboflow export directly.')
    if written:
        print('next: python yolo_prep.py build --images %s --labels %s --classes %s --out <dataset folder>' % (
            a.out_images or a.images, a.labels, ','.join(classes)))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    c = sp.add_parser('collect', help='gather thermal frames into one folder for labelling')
    c.add_argument('--src', default='~/dataset')
    c.add_argument('--out', default='~/yolo/to_label')
    c.add_argument('--every', type=int, default=1, help='take every Nth frame (2 = half)')
    c.add_argument('--max', type=int, default=0, help='at most this many frames per session (0 = all)')
    c.add_argument('--only', default='', help='comma list of session name prefixes to include')
    c.add_argument('--exclude', default='', help='comma list of session name prefixes to leave out')
    c.add_argument('--sub', default='thermal', choices=['thermal', 'rgb'], help='which camera folder to collect')
    b = sp.add_parser('build', help='make the YOLO train/val folders and data.yaml')
    b.add_argument('--images', default='~/yolo/to_label')
    b.add_argument('--labels', default='~/yolo/labels')
    b.add_argument('--classes', default=DEFAULT_CLASSES, help='in the SAME order as in the labelling tool')
    b.add_argument('--out', default='~/yolo/ds')
    b.add_argument('--neg', default=DEFAULT_NEG,
                   help='session name prefixes whose unlabelled images count as empty (nothing to detect)')
    b.add_argument('--test-prefix', default='test_')
    b.add_argument('--val-frac', type=float, default=0.2)
    b.add_argument('--seed', type=int, default=0)
    r = sp.add_parser('rfimport', help='bring labels from a Roboflow YOLOv8 export back to our image names')
    r.add_argument('--zip', required=True, help='the Roboflow export .zip (or its unzipped folder)')
    r.add_argument('--images', default='~/yolo/to_label')
    r.add_argument('--labels', default='~/yolo/labels')
    r.add_argument('--classes', default=DEFAULT_CLASSES, help='our class order (names must match Roboflow\'s, any case)')
    r.add_argument('--out-images', default='', help='copy the export\'s images here and use them instead of --images')
    a = ap.parse_args(argv)
    {'collect': cmd_collect, 'build': cmd_build, 'rfimport': cmd_rfimport}[a.cmd](a)


if __name__ == '__main__':
    main()
