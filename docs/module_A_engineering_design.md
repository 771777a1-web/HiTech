# Module A: engineering design (summary)

The submitted Module A document (PDF/DOCX, 10 Nov 2026) is the design baseline. This page gives the parts the
repository needs and points to where each is implemented. Differences between the design and what was built
are listed in [architecture.md](architecture.md#as-built-versus-the-module-a-design).

## Purpose and main specifications

A multirotor UAV (frame diagonal ≤ 10") flies a predefined route over an indoor ArUco marker field under PX4,
runs a YOLO detector on its NPU, detects a campfire prop and an additional object, computes each object's
position in the field's coordinates and shows it on a live web map with type, time and confidence; it returns
home on the operator's command. Targets from the Case 1 task: campfire mAP@0.5 ≥ 85 %, ≥ 10 FPS for > 90 % of
the time, coordinate error ≤ 0.5 m, every event logged with time, coordinates, type and confidence, ≥ 1 campfire
detection per flight, return on command.

## Key engineering decisions

| Decision | Reason | Implemented in |
|----------|--------|----------------|
| Drive PX4 through the SKYRIS `technic` ROS services (`navigate`, `land`, `get_telemetry`) | tested layer; flight safety stays with PX4; our software can fail without taking the aircraft with it | [`ground_station/index.html`](../ground_station/index.html) (route, return home) |
| Inference on the onboard NPU (YOLOv8n, 320 px, RKNN) | no video downlink, low latency; the task requires NPU/GPU processing | [`drone/fire_detector_node.py`](../drone/fire_detector_node.py) |
| Downward RGB camera as the detection sensor, thermal camera as a second channel | the venue campfire is a visual prop with no heat (defect D5) | [`drone/fire_detector.launch`](../drone/fire_detector.launch), [`drone/airael.sh`](../drone/airael.sh) |
| Geolocation from the camera pose in `aruco_map` | the field's own coordinates are the ones the 0.5 m requirement is measured in | [`drone/fire_geoloc.py`](../drone/fire_geoloc.py) |
| Web page served by the drone | no ground hardware beyond a browser | [`ground_station/index.html`](../ground_station/index.html), page server in [`drone/airael.sh`](../drone/airael.sh) |

## Team roles

| Participant | Role | Responsibilities |
|-------------|------|------------------|
| Mohammed Alhammadi | Programmer: computer vision, geolocation, ground station | dataset tools, YOLO training and RKNN export, detector node, geolocation, ground station, flight report, repository and README |
| Omar Alblooshi | Flight control and hardware engineer | PX4 set-up and parameters, airframe, mounts, wiring and power, sensor integration (thermal camera), drone services and boot unit, flight tests and safety, user manual and checklist, Module A–D documents |

## Components

| No. | Component | Function | Key specs |
|-----|-----------|----------|-----------|
| 1 | SKYRIS Technic 6S frame, four 2306 1650KV motors, 3-blade props with guards | carries the payload | supplied; take-off mass ≈ 1,250 g (estimated) |
| 2 | PX4 flight controller (FMU v4, Pixracer class) | stabilisation, route following, failsafes | TELEM2 ↔ OPi Pro Shield UART |
| 3 | Orange Pi 5 Pro 16 GB on the SKYRIS OPi Pro Shield | detection, geolocation, our services | RK3588S, 6 TOPS NPU |
| 4 | Mileseey TR256i thermal camera | second sensor channel | 256 × 192, 25 Hz, USB-C, 56° × 42° |
| 5 | ArUco navigation (`aruco_pose`) with the downward camera | position in the field's coordinates | markers 0.25 m, 9 × 5, pitch 0.75 m |
| 6 | VL53L1X rangefinder | height above the floor | 0–4 m; read 0.037 m resting on the table |
| 7 | Orange Pi Wi-Fi access point (10.42.0.1) and Ethernet (192.168.50.2) | link to the ground station | — |
| 8 | RadioMaster Pocket (ELRS) | manual override and kill switch | kill switch on its own channel |
| 9 | Ground laptop | browser, training and export | — |
| 10 | GNB 6S 3500 mAh LiPo | power | 22.2 V, 77.7 Wh |

## Original contribution

The geolocation routine ([`drone/fire_geoloc.py`](../drone/fire_geoloc.py)): a ray from the calibrated camera
through the box centre, rotated into `aruco_map` with tf at the image time, intersected with a plane at the
object's height, with sightings of the same object merged and their median reported; it falls back to the last
marker fix when markers drop out. Tested in [`tests/test_geoloc.py`](../tests/test_geoloc.py). Its accuracy
against single-frame projection in flight (MC5) is TODO.

## Readiness and repository checklists

The pre-test start-up checklist is section 1 of the [operating manual](operating_manual.md). Repository items:
README, licence, `.gitignore`, no broken links or missing modules (checked by `tests/test_repo.py`), commits by
each member (see the commit plan delivered with the repository).
