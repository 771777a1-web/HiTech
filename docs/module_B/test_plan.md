# Module B: test plan and procedures

System under test: the software in this repository, installed with `drone/install_drone.sh`, on the SKYRIS
Technic 6S. No code or hardware changes during a formal test. Values in [brackets] are to be confirmed with
the lead experts before testing starts; after that, thresholds and methods do not change.

**Reference set.** The seven characteristics MC1–MC7 and the modules FM1–FM3 below are the ones recorded as
approved in the team's notes of 11 Nov 2026. The Module A document, the earlier Module B report and the
defence slides use T1–T7 and M1–M3 for the same tests; the mapping is in the last section.

**Common initial conditions.** ArUco field 7.5 × 4.5 m (markers 100–144, 0.25 m, pitch 0.75 m, origin at the
field centre = marker 122); campfire prop and tree(s) placed on markers whose positions are known; battery
≥ 23.0 V; pre-flight checklist of the [operating manual](../operating_manual.md) complete;
`~/airael/airael.sh status` all green; ground station open at `http://<drone>:8020/`; drone clock set from the
laptop; `rosbag record` running (command in the operating manual); screen recording and phone video running.

## Mandatory characteristics

| ID | Characteristic (unit) | Threshold | Measured quantity and method | Pass criterion | Attempts |
|----|----------------------|-----------|------------------------------|----------------|----------|
| MC1 | Autonomous route: waypoints reached without pilot input (%) | 100 % of waypoints within 0.30 m, 0 pilot inputs | Ground station Route card: for each waypoint the mean horizontal error over the 1.5 s hold, from `get_telemetry` in `aruco_map` at 5 Hz. Route log CSV (`result`, `err_mean_m`). Pilot input = route aborted because the mode left OFFBOARD (command log). | every waypoint PASS, route not aborted | [3] |
| MC2 | Campfire detection accuracy, mAP@0.5 (%) | ≥ 85 % | `yolo detect val` of the deployed model's `best.pt` on the held-out validation sessions (split by session), campfire row, column mAP50 | campfire mAP50 ≥ 0.85 | [1] |
| MC3 | Additional object (tree) detected per pass (count) | ≥ 1 per pass | `flight_report.py <bag> --fire tree`: line T4 "N reported (new)" | ≥ 1 tree object per route pass | [3] |
| MC4 | Onboard processing rate: 1-s windows with ≥ 10 processed frames (%) | > 90 % of the flight | `flight_report.py <bag>`: line T2, counts `/fire/detections` messages per second after the first 5 s; seconds with none count as 0 | share > 90 % | [3] |
| MC5 | Object coordinate error (m) | ≤ 0.5 m | `flight_report.py <bag> --truth campfire=x,y tree=x,y`: line T3, distance between the last `/fire/objects` position and the marker position under the object | error ≤ 0.5 m for every object | [3] |
| MC6 | Live map: objects shown with type and time (%), latency (s) | 100 %, ≤ 2 s | Event log CSV: `latency_s` = receive time − image time; screen recording shows each object on the map with type and time | every reported object on the map; all latencies ≤ 2 s | [3] |
| MC7 | Return on operator command | starts moving ≤ 2 s, lands ≤ 0.5 m from home, 0 pilot inputs | Press **Return home** mid-route; command log lines "Return home: moving toward home X s after the command" and "Return home finished: landed X m from home" | both within limits, no pilot input | [3] |

### Procedures

**MC1.** 1) Place the drone on the take-off marker. 2) Route card: **Snake** (or **Corners**), altitude 1.5 m,
speed 0.5 m/s, hold 1.5 s, arrive 0.15 m, end "Return home and land". 3) **Start route** (twice).
4) After landing: **Download route log** and **Download** command log. 5) Read the Route summary line ("… · MC1 PASS/FAIL").

**MC2.** On the laptop: `yolo detect val model=$HOME/yolo/runs/fire_rgb/weights/best.pt data=$HOME/yolo/ds_rgb/data.yaml imgsz=320 | tee evidence/<date>_MC2_val.txt`.
Read the `campfire` row, mAP50. Attach `results.png` and `confusion_matrix.png` of the run.

**MC3, MC4, MC5.** 1) Write down the marker under each object (positions from the page map). 2) Start `rosbag record`.
3) Fly the MC1 route over the objects. 4) After landing stop the recording, then on the drone:
`python3 ~/airael/flight_report.py ~/airael/flights/f1.bag --truth campfire=<x>,<y> tree=<x>,<y>` and
`python3 ~/airael/flight_report.py ~/airael/flights/f1.bag --fire tree`. Keep both outputs and `f1_report.json`.

**MC6.** During the MC1 flight: screen-record the page. After landing: Event log → **Download CSV**; check every
object in `/fire/objects` appears in the CSV and on the recording, and every `latency_s` ≤ 2.

**MC7.** 1) Start the route. 2) Between waypoints 2 and 3 press **Return home**. 3) After landing download the command log.

## Functional modules

| Module | Independently verifiable function | Method | Pass criterion |
|--------|-----------------------------------|--------|----------------|
| FM1 Flight | flies a route of ArUco waypoints by itself and returns home | MC1 and MC7 procedures | MC1 and MC7 pass |
| FM2 Perception | camera frames reach the NPU detector and the campfire is detected on board at ≥ 10 FPS | camera part: `rostopic hz` on the thermal and RGB topics; detector: hold the drone over the campfire, `rostopic hz /fire/detections` and the detector pill shows `campfire` | camera rates steady; detector ≥ 10 FPS with a campfire detection |
| FM3 Geolocation and ground station | a detected object appears on the map at its position | campfire on a known marker, drone held ≥ 1 m above it with markers in view; read the map position and the event log | position within [0.5] m, on the map within [2] s |

## End-to-end scenario

Pre-flight checklist → **Start route** (Snake, 1.5 m, **Inspect bonfires** on at 1.0 m) → take-off → route with
detection → campfire and tree on the map and in the event log → the drone flies over the campfire, a photo
appears in the Detections tab → route resumes → return home → landing. Attempts: [3]. Permitted recovery:
battery change, restarting `airael.sh` between attempts. No code or hardware changes.

**Abnormal conditions (separate attempts):**

| Condition | How it is caused | Expected result |
|-----------|-----------------|-----------------|
| Pilot override | pilot switches flight mode on the RC during the route | route aborted ("pilot or failsafe took over"), no further commands from the page; kill switch stops the motors |
| Ground link loss | laptop Wi-Fi/Ethernet off for 10 s during the route | drone holds its last setpoint; detection and logging continue on board; the page reconnects and the route continues |
| Detector crash | `pkill -f fire_detector_node.py` during the route | detector back within 5 s (`respawn`), detector pill green again |

## Additional function (outside the mandatory list)

**Route inspection with photo capture.** When geolocation reports a campfire during a route, the drone leaves
the route, flies over the object at the chosen height, holds, takes a photo (RGB with boxes, RGB raw, thermal,
position, time) and returns to the route. Each object is photographed once (same id, or within 1 m of an
earlier photo). New software components: the `capture` command in `drone/dataset_server.py`, the inspection
logic and the Detections tab in `ground_station/index.html`. Verification: in the end-to-end flight, one photo
per campfire in the Detections tab, none duplicated, route completed.

## Mapping to the IDs in the earlier documents

| This plan | Module A | Earlier Module B report and slides | Note |
|-----------|----------|-----------------------------------|------|
| MC1 | No. 4 | M1 (within 0.2 m) | threshold here: mean error ≤ 0.30 m over the hold |
| MC2 | No. 1 | T1 | here measured on held-out sessions; T1 planned labelling the frames of the scored flight |
| MC3 | additional object | — | object is a tree (MC3 was approved with "person"; to confirm with the experts) |
| MC4 | No. 2 | T2 | same method (`flight_report.py` T2) |
| MC5 | No. 3 | T3 | same method (`flight_report.py` T3) |
| MC6 | No. 5 | T5, M3 | log completeness (Module A No. 6, T6) is printed by `flight_report.py` (T6) as supporting evidence |
| MC7 | No. 7 | T7 | — |
| — | — | T4 (flame per flight) | printed by `flight_report.py` (T4) |
