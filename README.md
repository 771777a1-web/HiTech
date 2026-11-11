# Airael — Flying Robotics Competition

Autonomous UAV for forest-fire hotspot monitoring, built for the **"Flying Robotics"** skill area,
**Case 1 — University 2035 (Autonomous Forest Fire Monitoring)**.

The drone flies a predefined route on its own, reads a thermal camera in real time, detects a
simulated flame (campfire) and at least one extra object with a neural network running on an
onboard NPU/GPU, works out each object's ground coordinates, and sends them to a web interface
that shows detections on a map and logs every event. On operator command it returns home.

## Status

| Area | Status |
|---|---|
| Autonomous route flight | Started |
| Thermal camera capture | Started |
| Flame detection (mAP@0.5 ≥ 85%) | Progress |
| Additional object detection | Progress |
| Onboard inference ≥ 10 FPS | ⬜ Not started |
| Object geolocation (error ≤ 0.5 m) | ⬜ Not started |
| Web map + event log | ⬜ Not started |
| Return on operator command | ⬜ Not started |

Full requirement-by-requirement tracking: [`docs/requirements-traceability.md`](docs/requirements-traceability.md).

## Repository layout

```
docs/               Competition task, platform notes, architecture, work log, test reports
  test-reports/     Results of each test flight / benchmark
  media/            Photos, screenshots, flight videos (large files → Git LFS or links)
flight/             Autonomous navigation: route following, return-to-home
  missions/         Route definitions
perception/         Thermal capture + neural-network detection
  models/           Trained weights / NPU-converted models (not committed if large)
  datasets/         Dataset description and sources (data itself kept outside git)
  training/         Training configs and notes
localization/       Converting detections in the image to ground coordinates
ground_station/     Web application: live map, detection list, event log
logs/               Flight and event logs (git-ignored, keep samples only)
scripts/            Setup, deployment and utility scripts
tests/              Automated tests and benchmarks
```

## Platform

Based on the Skyris platform — see [`docs/platform.md`](docs/platform.md) and the official
documentation: <https://docs.skyris.ru/technic6S/>.

## Team

| Name | Role |
|---|---|
| _TBD_ | _TBD_ |
