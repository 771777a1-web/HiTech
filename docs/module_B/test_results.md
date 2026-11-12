# Module B: test results

Status on 12 Nov 2026: software tests and bench measurements are done; **no formal flight test has been
recorded yet**. Every measured field without a record is **TODO** with the command that produces it.
Procedures and thresholds: [test_plan.md](test_plan.md). Raw records: [evidence/](../../evidence/README.md).

## Mandatory characteristics

| ID | Threshold | Measured | Result | Attempt | Evidence |
|----|-----------|----------|--------|---------|----------|
| MC1 | 100 % of waypoints ≤ 0.30 m, 0 pilot inputs | TODO: ground station → Route card → Download route log | — | — | — |
| MC2 | campfire mAP@0.5 ≥ 85 % | TODO: `yolo detect val model=$HOME/yolo/runs/fire_rgb/weights/best.pt data=$HOME/yolo/ds_rgb/data.yaml imgsz=320` (campfire row) | — | — | dataset and training record: [2026-11-12_dataset_and_model.txt](../../evidence/2026-11-12_dataset_and_model.txt) |
| MC3 | ≥ 1 tree per pass | TODO: `python3 ~/airael/flight_report.py <bag> --fire tree` (line T4) | — | — | — |
| MC4 | > 90 % of 1-s windows ≥ 10 FPS | TODO for a flight: `python3 ~/airael/flight_report.py <bag>` (line T2). Bench, 12 Nov 2026: 30.09 Hz average on `/fire/detections` over 158 messages, detector log 30.0–30.1 FPS, 19.4–26.2 ms per frame | bench only | — | [2026-11-12_detector_rgb_bench.txt](../../evidence/2026-11-12_detector_rgb_bench.txt) |
| MC5 | ≤ 0.5 m | TODO: `python3 ~/airael/flight_report.py <bag> --truth campfire=<x>,<y> tree=<x>,<y>` (line T3) | — | — | — |
| MC6 | 100 % on the map, latency ≤ 2 s | TODO: event log CSV (`latency_s`) and screen recording | — | — | — |
| MC7 | starts ≤ 2 s, lands ≤ 0.5 m from home, 0 pilot inputs | TODO: command log lines "Return home: moving toward home …" and "Return home finished: landed … m from home" | — | — | — |

## Functional modules

| Module | Measured | Result | Evidence |
|--------|----------|--------|----------|
| FM1 Flight | TODO (MC1 and MC7 flights) | — | — |
| FM2 Perception | camera part, 11 Nov 2026: thermal camera 25.01 Hz over 1428 frames, max gap 0.061 s; RGB compressed topic 30 Hz after the D4 fix. Detector on the NPU with the deployed model, 12 Nov 2026: 30 FPS, 19–26 ms per frame, on the RGB camera. Campfire detection with the drone held over the prop: TODO | camera part pass; detector rate pass on the bench | thermal record on the laptop (`~/evidence/2026-11-11_ST-FM2_a1/`, TODO copy); [detector bench](../../evidence/2026-11-12_detector_rgb_bench.txt) |
| FM3 Geolocation and ground station | bench, 12 Nov 2026: node running, 1 object reported (4 events); 67 of 74 detections not placed because the drone was below the object plane (D10). Positional accuracy: TODO | not measured | [detector bench](../../evidence/2026-11-12_detector_rgb_bench.txt) |

## End-to-end scenario and abnormal conditions

| Scenario | Attempts used | Outcome | Non-critical failures and recovery |
|----------|---------------|---------|-------------------------------------|
| Full mission | TODO of [3] | TODO | TODO |
| Pilot override | TODO | TODO | TODO |
| Ground link loss | TODO | TODO | TODO |
| Detector crash | TODO | TODO | TODO |
| Additional function: route inspection with photo | TODO | TODO | TODO |

## Software tests

`python3 -m unittest discover -s tests -v`, run on 12 Nov 2026 on a development computer without ROS
(Python 3.13, NumPy 2.5, OpenCV 5.0, Node.js 22): **39 tests, all pass**. Save the output on the test day as
`evidence/<date>_software_tests.txt`.

| Group | What is checked |
|-------|-----------------|
| Detector (6) | YOLOv8 output decoding, empty/bad outputs, per-class NMS, letterbox 640×480 → 320, one frame through the node with a stand-in NPU (box mapped back to camera pixels), node defaults = deployed model |
| Geolocation (14) | quaternion, centre pixel under the camera, offset scales with height, rays that miss the floor, distortion, tracker confirm/merge/false-alarm/median update, node event fields, low score ignored, no pose → no event, last marker fix used when markers drop out |
| Flight report (6) | FPS share with gaps, too few frames, event completeness, position errors by class, truth parsing |
| Dataset tool (3) | split by session with negatives and bad label lines, Roboflow import re-numbered by name, old 256×384 thermal frames cropped |
| Repository (10) | shell scripts parse, `airael.sh` usage, installer copies every file, ground-station JavaScript parses, Python compiles, same classes/camera/model/ports in every file, every Markdown link and repository path exists |

Integration tests that ran on the drone (not automated): `airael.sh start --detector` brought up all five
services, the detector ran on `/main_camera/image_raw` at about 30 FPS, geolocation published `/fire/events`
([record](../../evidence/2026-11-12_detector_rgb_bench.txt)).

## Conclusion

TODO after the flights: which characteristics passed, which defects were found in flight and how they were corrected.
