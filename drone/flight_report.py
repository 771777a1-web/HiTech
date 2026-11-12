#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Airael Module B: test numbers from one flight recording (rosbag).

Record during the flight (on the drone, own terminal, Ctrl+C after landing):
  rosbag record -O ~/airael/flights/f1 /fire/detections /fire/events /fire/objects \
      /mavros/state /mavros/local_position/pose /airael/thermal/compressed /rosout

Then (on the drone):
  python3 ~/airael/flight_report.py ~/airael/flights/f1.bag \
      --truth campfire=1.50,0.75 tree=-0.75,1.50 --fire campfire

--truth  tape-measured object positions on the ArUco map, class=x,y (repeat for each object)
--fire   class name of the flame in your model (campfire for the deployed RGB model)

Prints T2 (FPS), T3 (position error), T4 (flame events), T6 (event completeness), M2 (confidence + FPS)
and writes <bag>_report.json next to the bag.
In docs/module_B/test_plan.md: T2 = MC4, T3 = MC5, T4/T6 = MC6 evidence, M2 = FM2.
"""

import argparse
import json
import math
import sys


# ---------------------------------------------------------------- pure analysis (no ROS needed)
def fps_share(stamps, skip_s=5.0, fps_min=10.0):
    """Share of whole seconds with >= fps_min processed frames. First skip_s seconds and the last
    partial second are excluded. Seconds with no frames at all count as 0 FPS."""
    if len(stamps) < 2:
        return None
    stamps = sorted(stamps)
    t0 = stamps[0] + skip_s
    n_sec = int(math.floor(stamps[-1] - t0))
    if n_sec <= 0:
        return None
    counts = [0] * n_sec
    for t in stamps:
        k = int(math.floor(t - t0))
        if 0 <= k < n_sec:
            counts[k] += 1
    good = sum(1 for c in counts if c >= fps_min)
    return {'seconds': n_sec, 'seconds_ok': good, 'share_pct': round(100.0 * good / n_sec, 1),
            'min_fps': min(counts), 'mean_fps': round(sum(counts) / float(n_sec), 1)}


def finite(v):
    try:
        return v is not None and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def event_completeness(events):
    """T6: every event needs time, x, y, type and confidence."""
    ok = 0
    bad = []
    for e in events:
        good = (finite(e.get('stamp')) and float(e['stamp']) > 0 and finite(e.get('x')) and finite(e.get('y'))
                and bool(str(e.get('class_name', '')).strip()) and finite(e.get('score')))
        if good:
            ok += 1
        else:
            bad.append(e)
    return {'events': len(events), 'complete': ok,
            'pct': round(100.0 * ok / len(events), 1) if events else None, 'incomplete_examples': bad[:3]}


def position_errors(objects, truth):
    """T3: for each tape-measured object, the nearest reported object of the same class."""
    out = []
    used = set()
    for cls, tx, ty in truth:
        best, bd = None, None
        for i, o in enumerate(objects):
            if i in used or str(o.get('class_name', '')).lower() != cls.lower():
                continue
            d = math.hypot(float(o['x']) - tx, float(o['y']) - ty)
            if bd is None or d < bd:
                best, bd = i, d
        if best is None:
            out.append({'class': cls, 'truth': [tx, ty], 'found': False})
        else:
            used.add(best)
            o = objects[best]
            out.append({'class': cls, 'truth': [tx, ty], 'found': True, 'reported': [o['x'], o['y']],
                        'error_m': round(bd, 3), 'hits': o.get('hits'), 'id': o.get('id')})
    extra = [o for i, o in enumerate(objects) if i not in used]
    return out, extra


def parse_truth(items):
    truth = []
    for it in items or []:
        try:
            cls, xy = it.split('=', 1)
            x, y = xy.split(',')
            truth.append((cls.strip(), float(x), float(y)))
        except ValueError:
            sys.exit('bad --truth "%s": use class=x,y, e.g. campfire=1.5,0.75' % it)
    return truth


# ---------------------------------------------------------------- bag reading
def read_bag(path):
    import rosbag  # only needed here (ROS Noetic on the drone)
    dets, events, objects = [], [], []
    with rosbag.Bag(path) as bag:
        for topic, msg, t in bag.read_messages(topics=['/fire/detections', '/fire/events', '/fire/objects']):
            try:
                d = json.loads(msg.data)
            except ValueError:
                continue
            if topic == '/fire/detections':
                st = float(d.get('stamp') or 0) or t.to_sec()
                dets.append((st, d.get('detections', []), d.get('proc_ms')))
            elif topic == '/fire/events':
                d['_bag_t'] = t.to_sec()
                events.append(d)
            else:
                objects = d   # keep the last list
    return dets, events, objects


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('bag')
    ap.add_argument('--truth', nargs='*', default=[], help='class=x,y per object (ArUco map, metres)')
    ap.add_argument('--fire', default='campfire', help='flame class name (default campfire)')
    ap.add_argument('--conf', type=float, default=0.45, help='M2 confidence threshold (default 0.45)')
    ap.add_argument('--skip', type=float, default=5.0, help='seconds excluded at the start for T2 (default 5)')
    ap.add_argument('--fps-min', type=float, default=10.0)
    ap.add_argument('--max-err', type=float, default=0.5, help='T3 threshold in metres (default 0.5)')
    a = ap.parse_args()

    truth = parse_truth(a.truth)
    dets, events, objects = read_bag(a.bag)
    fire = a.fire.lower()
    rep = {'bag': a.bag, 'frames': len(dets)}

    print('Flight: %s' % a.bag)
    if not dets:
        print('  no /fire/detections in the bag: was the detector running and the topic recorded?')
    else:
        dur = dets[-1][0] - dets[0][0]
        print('  detector frames %d over %.1f s' % (len(dets), dur))

    # T2
    f = fps_share([d[0] for d in dets], a.skip, a.fps_min)
    rep['T2'] = f
    if f:
        print('\nT2 FPS: %.1f %% of %d s at >= %g FPS (min %d, mean %.1f)  -> %s'
              % (f['share_pct'], f['seconds'], a.fps_min, f['min_fps'], f['mean_fps'],
                 'PASS' if f['share_pct'] > 90 else 'FAIL'))
    else:
        print('\nT2 FPS: not enough frames')

    # M2
    fire_scores = [x['score'] for _, ds, _ in dets for x in ds if str(x.get('class_name', '')).lower() == fire]
    fire_frames = sum(1 for _, ds, _ in dets if any(str(x.get('class_name', '')).lower() == fire for x in ds))
    m2 = {'fire_frames': fire_frames, 'max_conf': round(max(fire_scores), 3) if fire_scores else None,
          'frames_over_conf': sum(1 for _, ds, _ in dets
                                  if any(str(x.get('class_name', '')).lower() == fire and x['score'] >= a.conf for x in ds)),
          'mean_fps': f['mean_fps'] if f else None}
    rep['M2'] = m2
    print('\nM2 %s: seen in %d frames, max confidence %s, %d frames >= %.2f, mean %s FPS  -> %s'
          % (a.fire, fire_frames, m2['max_conf'], m2['frames_over_conf'], a.conf, m2['mean_fps'],
             'PASS' if m2['frames_over_conf'] and f and f['mean_fps'] >= a.fps_min else 'FAIL'))

    # T4
    new_fire = [e for e in events if e.get('kind') == 'new' and str(e.get('class_name', '')).lower() == fire]
    rep['T4'] = {'fire_objects_reported': len(new_fire),
                 'fire_events_total': sum(1 for e in events if str(e.get('class_name', '')).lower() == fire)}
    print('\nT4 flame: %d reported (new), %d events incl. updates  -> %s'
          % (len(new_fire), rep['T4']['fire_events_total'], 'PASS' if new_fire else 'FAIL'))

    # T6
    c = event_completeness(events)
    rep['T6'] = c
    print('\nT6 events: %d, complete %d (%s %%)  -> %s'
          % (c['events'], c['complete'], c['pct'], 'PASS' if c['events'] and c['complete'] == c['events'] else 'FAIL'))
    for e in c['incomplete_examples']:
        print('    incomplete:', e)

    # T3
    print('\nT3 positions (last /fire/objects):')
    if not objects:
        print('  no objects reported')
    for o in objects:
        print('  #%s %-10s (%.2f, %.2f)  hits %s  spread %s m' % (o.get('id'), o.get('class_name'), o['x'], o['y'],
                                                               o.get('hits'), o.get('spread')))
    if truth:
        errs, extra = position_errors(objects, truth)
        rep['T3'] = {'objects': errs, 'extra_objects': extra}
        for r in errs:
            if r['found']:
                print('  %-10s truth (%.2f, %.2f) -> error %.2f m  %s' % (r['class'], r['truth'][0], r['truth'][1],
                                                                        r['error_m'], 'PASS' if r['error_m'] <= a.max_err else 'FAIL'))
            else:
                print('  %-10s truth (%.2f, %.2f) -> NOT FOUND  FAIL' % (r['class'], r['truth'][0], r['truth'][1]))
        if extra:
            print('  extra objects with no tape-measured match (false or duplicate): %d' % len(extra))
    else:
        print('  (add --truth class=x,y ... to get the errors)')

    # event list for the report / T5 cross-check
    print('\nEvent log:')
    for e in events:
        print('  %.2f  %-6s %-10s conf %.2f  (%.2f, %.2f)' % (float(e.get('stamp') or 0), e.get('kind', ''),
                                                            e.get('class_name'), float(e.get('score') or 0),
                                                            float(e.get('x') or 0), float(e.get('y') or 0)))

    out = a.bag[:-4] + '_report.json' if a.bag.endswith('.bag') else a.bag + '_report.json'
    with open(out, 'w') as fh:
        json.dump(rep, fh, indent=2)
    print('\nSaved %s' % out)


if __name__ == '__main__':
    main()
