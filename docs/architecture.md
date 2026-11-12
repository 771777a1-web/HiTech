# Architecture, interfaces and data formats

This describes the system as built and run on the drone. Where it differs from the Module A design
document, the table at the end says how and why.

## Components

| Component | Ours / third-party | Input | Output |
|-----------|-------------------|-------|--------|
| SKYRIS Technic 6S airframe, PX4 flight controller (FMU v4), RC with kill switch | supplied | RC, MAVLink setpoints | flight |
| SKYRIS ROS stack (`technic.service`): `technic` services `navigate`, `land`, `get_telemetry`; `aruco_pose`; MAVROS; camera drivers; `rosbridge` :9090; `web_video_server` :8080 | supplied | cameras, PX4 | pose in `aruco_map`, ROS services, image topics |
| Downward RGB camera, `/main_camera/image_raw`, 640×480, 30 Hz | supplied | — | images for ArUco navigation and our detector |
| Mileseey TR256i thermal camera, `/second_camera/second_camera/image_raw`, 256×192, 25 Hz | added by the team | — | thermal images (dashboard, dataset, photos) |
| VL53L1X rangefinder, `/rangefinder/range`, 0–4 m | supplied | — | height above the floor |
| **fire_detector** ([`drone/fire_detector_node.py`](../drone/fire_detector_node.py)) | ours | RGB image | `/fire/detections` JSON, every frame |
| **fire_geoloc** ([`drone/fire_geoloc.py`](../drone/fire_geoloc.py)) | ours | detections, `camera_info`, tf | `/fire/events`, `/fire/objects` JSON |
| **dataset_server** ([`drone/dataset_server.py`](../drone/dataset_server.py)) | ours | commands from the page, cameras, pose, rangefinder | dataset sessions, object photos, `/airael/dataset/status` |
| **airael.sh** ([`drone/airael.sh`](../drone/airael.sh)) | ours | — | starts and supervises our processes; page server on :8020; thermal JPEG republisher `/airael/thermal/compressed` |
| **Ground station** ([`ground_station/index.html`](../ground_station/index.html)) | ours | rosbridge, HTTP | map, route flight, return home, logs, camera, dataset, photo gallery |

## Operating sequence (one flight)

1. `technic.service` starts with the drone; `airael.sh start --detector` (by hand or as `airael.service`) starts our nodes.
2. The operator opens `http://<drone>:8020/`, the page connects to rosbridge on :9090 and polls `get_telemetry` (frame `aruco_map`) at 5 Hz.
3. **Start route**: the page calls `navigate` (frame `body`, `auto_arm`) to take off, then one `navigate` per waypoint in `aruco_map`.
   A waypoint is reached within 0.15 m, held 1.5 s; the mean error over the hold must be ≤ 0.30 m (MC1).
4. Each RGB frame goes to the NPU (YOLOv8n, 320 px, letterbox); every frame is published on `/fire/detections`.
5. `fire_geoloc` turns each box centre into a ray, rotates it into `aruco_map` with tf at the image time, and intersects it with
   a horizontal plane at the object's height (campfire 0.15 m, tree 0.6 m). Two sightings within 1.5 s confirm an object;
   its position is the median of the last 15 sightings; it is re-sent every 2 s while seen.
6. The page draws each object on the map with type, confidence and first-seen time, and appends the event log.
   Optional: when a campfire is reported during a route, the drone flies over it at the inspection height, holds,
   `dataset_server` takes a photo (RGB with boxes, RGB raw, thermal), and the route continues.
7. **Return home**: `navigate` to the take-off point at the current height, then `land` within 0.15 m of home.
   The page logs the time to first motion and the landed distance (MC7).

## Interfaces

| Interface | Type / format | Producer → consumer |
|-----------|---------------|---------------------|
| `/main_camera/image_raw` | sensor_msgs/Image bgr8 640×480 | SKYRIS → fire_detector, dataset_server |
| `/main_camera/camera_info` | sensor_msgs/CameraInfo (SKYRIS calibration) | SKYRIS → fire_geoloc |
| `/second_camera/second_camera/image_raw` | sensor_msgs/Image bgr8 256×192 | SKYRIS → dataset_server, `airael_thermal_compress` |
| tf `aruco_map` ← `main_camera_optical`, `aruco_map` ← `map` | tf2 | SKYRIS (`aruco_pose`) → fire_geoloc |
| `/fire/detections` | std_msgs/String JSON, see below | fire_detector → fire_geoloc, dataset_server, page |
| `/fire/events` | std_msgs/String JSON, see below | fire_geoloc → page |
| `/fire/objects` (latched) | std_msgs/String JSON list of tracked objects | fire_geoloc → `flight_report.py` |
| `/fire/reset` | std_msgs/Empty | operator → fire_geoloc (clears tracked objects) |
| `/airael/dataset/cmd`, `/airael/dataset/status` | std_msgs/String JSON | page ↔ dataset_server |
| `/airael/thermal/compressed` | sensor_msgs/CompressedImage | `airael_thermal_compress` → page |
| `/navigate`, `/land`, `/get_telemetry` | SKYRIS `technic` services. `navigate` takes only `x, y, z, yaw, speed, frame_id, auto_arm` | page → SKYRIS → PX4 |
| rosbridge WebSocket | TCP 9090 | page ↔ ROS |
| page server | HTTP 8020 (`python3 -m http.server`, `--bind 0.0.0.0`) | drone → browser; also serves `captures/` photos |
| web_video_server | HTTP 8080 (fallback camera view) | SKYRIS → page |
| Companion computer ↔ flight controller | UART (OPi Pro Shield ↔ TELEM2), MAVLink 2, driven by SKYRIS `technic` | — |

**`/fire/detections`**, one message per processed frame (also with no detections):

```json
{"stamp": 1794464345.64, "seq": 12, "width": 640, "height": 480, "proc_ms": 21.2,
 "detections": [{"class_id": 0, "class_name": "campfire", "score": 0.91,
                 "bbox": [x1, y1, x2, y2], "center": [cx, cy]}]}
```

**`/fire/events`**, one message per new object and one update every 2 s while it is seen:

```json
{"stamp": 1794464345.64, "class_name": "campfire", "score": 0.91, "x": 1.27, "y": -0.50,
 "id": 1, "kind": "new", "hits": 2, "spread": 0.01, "cam_z": 1.48, "plane_z": 0.15}
```

`stamp` is the camera image time (s), `x`, `y` are metres in `aruco_map` (origin at the field centre, marker 122).
The ground station's event log CSV adds `received_s` and `latency_s` (receive time minus image time; the drone
clock must be set from the laptop for this to be meaningful).

## Settings that change without code

| What | How |
|------|-----|
| Model file, class list, input size, detector camera | `MODEL=… CLASSES='[…]' SIZE=… DET_INPUT=… ~/airael/airael.sh start --detector` (or `roslaunch yolo_face fire_detector.launch model:=… classes:=… size:=… input:=… conf:=…`) |
| Thermal camera topic, page port, page folder, dataset server path | `THERMAL_IN`, `GS_PORT`, `GS_DIR`, `DATASET_PY` environment variables of `airael.sh` |
| Geolocation: object heights, merge radius, sightings to confirm, minimum score, map frame | ROS private params of `fire_geoloc.py` (`_object_heights`, `_merge_radius`, `_min_hits`, `_min_score`, `_map_frame`), and `GEO_HFOV` in `airael.sh` for a camera without calibration |
| Route, altitude, speed, hold time, arrival tolerance, end action, inspection height | ground station Route and Control cards (kept in the browser) |
| Drone address | ground station header field, or `?host=` in the page URL |

## Two connection configurations

| Configuration | Status |
|---------------|--------|
| Laptop on the drone's Ethernet (laptop 192.168.50.1, drone 192.168.50.2): page, rosbridge and SSH | used throughout development and the bench test of 12 Nov 2026 ([evidence](../evidence/2026-11-12_detector_rgb_bench.txt)) |
| Laptop on the drone's Wi-Fi access point (drone 10.42.0.1) | same software, no change; **not yet tested** (TODO before the formal test) |
| Detector on the thermal camera instead of RGB (`DET_INPUT=/second_camera/second_camera/image_raw`, a thermal model) | supported by the launch file and `airael.sh`; no thermal model was trained |

## Failure handling

| Failure | Behaviour |
|---------|-----------|
| Pilot changes flight mode or a PX4 failsafe takes over during a route | the page sees the mode leave OFFBOARD and aborts the route ("pilot or failsafe took over"); it sends no further commands |
| Drone disarms during a route | route aborted |
| Waypoint not reached in time (2 × distance/speed + 15 s) | route paused, drone told to hold |
| Ground link lost | the drone holds its last setpoint (SKYRIS `navigate`); our nodes keep running; the page reconnects every 2 s and the route continues when telemetry is back |
| Markers out of view | `fire_geoloc` uses the last marker fix (`aruco_map` ← `map`) and warns after 30 s; navigation is SKYRIS/PX4's |
| Detector process dies | `respawn="true"` in the launch file: back after 2 s |
| Detection off-plane (drone too low, camera not down) | the event is not created; the log says why (D10) |
| Emergency | RC kill switch; PX4 failsafes (RC loss → land, to be set in QGroundControl: see the operating manual) |

## Strengths and limitations

- **Strength: flight safety is separate from detection.** PX4 and the SKYRIS services fly the drone; if our detector or page stops, the drone holds or the pilot takes over.
- **Strength: detection and localisation run on board.** Only small JSON messages leave the drone; the measured detector rate on the NPU is about 30 FPS at 19–26 ms per frame ([evidence](../evidence/2026-11-12_detector_rgb_bench.txt)).
- **Limitation: needs the ArUco field.** Outdoors this would be GNSS/RTK.
- **Limitation: the route is run by the browser.** If the page is closed mid-route, the drone holds at its last waypoint instead of finishing the route.
- **Limitation: the campfire is detected in RGB, not thermal** (the venue prop gives off no heat; defect D5).

## As built versus the Module A design

| Module A (design) | As built | Why |
|-------------------|----------|-----|
| Web app with Flask and Leaflet on port 5000 | single HTML page served by `python3 -m http.server` on 8020, talking to ROS through rosbridge | nothing to install on the drone, which has no internet |
| Optional MQTT cloud copy (`ground/mqtt_bridge.py`) | not implemented | time; the A2 cloud aspect is not claimed |
| `config/params.yaml`, `onboard/requirements.txt`, `catkin_make` | settings by `airael.sh` environment variables and launch arguments; files copied by `drone/install_drone.sh` into the existing SKYRIS workspace | no build step and no Skyris file overwritten |
| CVAT for labelling | makesense.ai (thermal) and Roboflow (RGB, the deployed model) | browser tools, no install |
| Same-object merge within 1 m, median of the last 5 | merge within 0.6 m, median of the last 15, confirmed after 2 sightings | tuned in the bench tests |
| Height above ground from `/rangefinder/range` | camera pose from tf (`aruco_map`), intersected with a plane at the object's height | uses the SKYRIS-calibrated camera and frames directly |
| Bench run on a rosbag as second configuration | not done; Ethernet and Wi-Fi links are the two configurations (Wi-Fi untested) | time |
| "Detection degraded" flag | the page shows detector FPS in a coloured pill (green ≥ 10 FPS, amber below) | — |
| Return switch on RC channel 7 | Return home is a button in the page; the pilot uses the RC mode switch and kill switch | — |

## Third-party components

See [LICENSE](../LICENSE). The SKYRIS software, ROS, OpenCV, the RKNN runtime and PX4 are used as they are on the
drone image and are not part of this repository. Ultralytics YOLOv8 is used on the laptop for training and export only.
