# perception

Thermal image capture and neural-network object detection, running onboard.

**Covers:** R2 (thermal capture), R3 (flame mAP@0.5 ≥ 85%), R4 (additional object),
R5 (≥ 10 FPS on NPU/GPU for > 90% of time).

## Classes

| ID | Class | Notes |
|---|---|---|
| 0 | campfire | Simulated flame — required |
| 1 | _TBD_ | Team-selected additional object (e.g. vehicle, person) |

## Pipeline

1. Read frame from thermal camera (with timestamp)
2. Pre-process (normalisation / colour map, resize to model input)
3. Run YOLO on the NPU
4. Output detections → `localization/`
5. Record per-frame inference time to prove the FPS requirement

## Folders

- `models/` — trained and NPU-converted weights (large files not committed; store links)
- `datasets/` — description of datasets, sources, labelling rules, splits
- `training/` — training configs, hyper-parameters, results (mAP, PR curves)
