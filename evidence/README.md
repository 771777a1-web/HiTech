# Evidence

Raw records behind every number in the [results](../docs/module_B/test_results.md). Only records that
exist are in this folder; everything else is listed below as **TODO** with the command that produces it.
Large files (rosbags, videos, datasets, model weights) stay out of git: put them on the team drive and
link them here.

## In this folder

| File | What it is | Date |
|------|-----------|------|
| [2026-11-12_detector_rgb_bench.txt](2026-11-12_detector_rgb_bench.txt) | `airael.sh start --detector` output, detector rate (`rostopic hz /fire/detections`), detector and geolocation logs, deployed RGB model, drone on the bench | 12 Nov 2026 |
| [2026-11-12_dataset_and_model.txt](2026-11-12_dataset_and_model.txt) | dataset import and split (186 images, 333 boxes), training excerpt, export to `.rknn` (output shape `(1, 6, 2100)`) | 11–12 Nov 2026 |

## Kept on the team laptop, to be copied here (TODO)

| Record | Where it is now | Used for |
|--------|-----------------|----------|
| ST-FM2 camera test: thermal camera 25.01 Hz over 1428 frames, max gap 0.061 s | `~/evidence/2026-11-11_ST-FM2_a1/` on the laptop | camera part of FM2 |
| Final validation table of `best.pt` | produce: `yolo detect val model=$HOME/yolo/runs/fire_rgb/weights/best.pt data=$HOME/yolo/ds_rgb/data.yaml imgsz=320` | MC2 |
| `results.png`, `confusion_matrix.png` of the training run | `~/yolo/runs/fire_rgb/` on the laptop | MC2, Module D |

## To record during the flights (TODO)

Name each item `<date>_<test>_<attempt>`, e.g. `2026-11-12_MC1_a1_route_log.csv`.

| Record | How to produce it | Used for |
|--------|-------------------|----------|
| Route log CSV | ground station → Route card → **Download route log** | MC1 |
| Command log CSV | ground station → Command log → **Download** (contains the Return-home timing lines) | MC1 (pilot inputs), MC7 |
| Event log CSV | ground station → Event log → **Download CSV** (`latency_s` column) | MC6 |
| Flight bag | on the drone: `rosbag record -O ~/airael/flights/f1 /fire/detections /fire/events /fire/objects /mavros/state /mavros/local_position/pose /airael/thermal/compressed /rosout` | MC3, MC4, MC5 |
| Flight report | on the drone: `python3 ~/airael/flight_report.py ~/airael/flights/f1.bag --truth campfire=<x>,<y> tree=<x>,<y>` → `f1_report.json` | MC4, MC5, log completeness |
| Tree report | `python3 ~/airael/flight_report.py ~/airael/flights/f1.bag --fire tree` (line T4 = trees reported) | MC3 |
| Photos of objects | ground station → Detections tab (stored on the drone in `~/ground_station/captures/`) | MC6, Module D |
| Screen recording of the ground station and an uninterrupted phone video of the formal test | screen recorder on the laptop; phone | MC6, B criteria (photos, video) |
| Pre-flight check | on the drone: `~/airael/airael.sh status` (save the output) | pre-test checklist |
