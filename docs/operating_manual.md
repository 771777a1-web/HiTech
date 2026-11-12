# Operating manual

For the operator at the flying field. Two people: the **pilot** holds the RC transmitter with the kill switch
for the whole flight; the **operator** uses the ground station in a browser. Installation is in the
[deployment guide](deployment_guide.md).

Machines: **drone** = the Orange Pi on the aircraft (`ssh orangepi@192.168.50.2` over Ethernet, or
`10.42.0.1` over the drone's Wi-Fi); **laptop** = the ground computer with the browser.

## 1. Pre-flight checklist

| # | Check | How | OK when |
|---|-------|-----|---------|
| 1 | Battery | voltmeter or the page's Battery field | 6S, at least 23.0 V |
| 2 | Props, guards, camera and thermal camera mounts, cables | by hand | nothing loose; thermal camera tape holds |
| 3 | Kill switch and RC failsafe | pilot, props off | motors stop on the kill switch; QGroundControl → Safety: RC loss = Land, 2 s |
| 4 | PX4 battery cells and disarm after landing (defect D3) | drone: `rosrun mavros mavparam get BAT1_N_CELLS` and `rosrun mavros mavparam get COM_DISARM_LAND` | `6` and a value above `0` |
| 5 | Drone clock | laptop: `ssh -t orangepi@192.168.50.2 "sudo date -s @$(date +%s)"` | event times and latency are correct |
| 6 | Drone on the take-off point inside the marker field, nose along +x | look at the page map | the drone arrow is inside the field, position not jumping |
| 7 | Our services | drone: `~/airael/airael.sh status` | gs, thermal, dataset, detector, geoloc running; rosbridge :9090; topics `/fire/detections` and `/fire/events` |
| 8 | Page | laptop browser `http://192.168.50.2:8020/`, then **Ctrl+Shift+R** | header shows `v5 · inspect`; pills: rosbridge green, FCU connected, Detector ≥ 10 FPS |
| 9 | Recording for evidence | drone, second terminal: the `rosbag record` command in section 3 | running |

## 2. Start-up

1. Power the drone and wait about one minute for the SKYRIS stack (`technic.service`).
2. Connect the laptop: Ethernet cable (laptop address 192.168.50.1) or the drone's Wi-Fi.
3. On the drone, start our services if they are not started at boot:
   ```bash
   ~/airael/airael.sh start --detector
   ```
   It waits up to 90 s for ROS and rosbridge, stops the SKYRIS `rknn_face` demo (it would share the NPU),
   and starts: page server :8020, thermal JPEG for the page, dataset server, detector, geolocation.
4. Open `http://192.168.50.2:8020/` (or `http://10.42.0.1:8020/`). If the Drone field is empty, type the address and press **Connect**.
5. Camera card: **Downward camera + detections**. Boxes appear on the live picture when the detector sees something.

## 3. Normal operation

**Record the flight** (drone, own terminal; stop with Ctrl+C after landing):
```bash
rosbag record -O ~/airael/flights/f1 /fire/detections /fire/events /fire/objects \
    /mavros/state /mavros/local_position/pose /airael/thermal/compressed /rosout
```

**Fly a route (MC1):**
1. Route card: type marker IDs (e.g. `100 104 108 144`), or press **Corners** or **Snake**.
2. Set Altitude (default 1.5 m; limits 0.5–2.5 m) and Speed (≤ 1 m/s) in the Control card.
3. Optional: tick **Inspect bonfires found on the way**, set the inspection height and hold time.
4. Press **Start route** twice (the second press confirms). From the ground the drone takes off by itself.
5. Watch the route table: each waypoint shows PASS/FAIL and its mean error. Objects appear on the map with
   type, confidence and first-seen time, and in the event log with latency.
6. At the end the drone returns home and lands (or lands / hovers, as chosen in **At the end**).

**Return home at any time (MC7):** press **Return home**. The command log shows the time until the drone
starts moving and, after landing, the distance from home.

**Manual control from the page:** Take off (press twice), Fly to target (click the map), Hold position, Land (press twice).
Targets outside the field limits are clamped.

**After the flight, save the evidence:** Route card → **Download route log**; Event log → **Download CSV**;
Command log → **Download**; Ctrl+C the rosbag, then on the drone:
```bash
python3 ~/airael/flight_report.py ~/airael/flights/f1.bag --truth campfire=<x>,<y> tree=<x>,<y>
python3 ~/airael/flight_report.py ~/airael/flights/f1.bag --fire tree
```
Put the files in `evidence/` with the date and attempt in the name (see [evidence/README.md](../evidence/README.md)).

**Recording a dataset:** Dataset tab → click a label (keys 1–4) to record a session, **S** or **Esc** to stop.
Copy to the laptop with the `rsync` line shown on the tab.

## 4. Safe shutdown

1. Land (Return home or **Land**) and let PX4 disarm. The pilot confirms disarmed and keeps the kill switch on.
2. Download the logs from the page (section 3).
3. Stop the recording (Ctrl+C) and our services:
   ```bash
   ~/airael/airael.sh stop
   ```
4. Shut the computer down before unplugging the battery:
   ```bash
   sudo shutdown now
   ```
   Wait about 10 s, then unplug the battery.

## 5. Typical errors

| Symptom | Cause | What to do |
|---------|-------|-----------|
| Page does not load from the laptop | page server not running, or bound to 127.0.0.1 (D7) | drone: `~/airael/airael.sh status`; restart with `~/airael/airael.sh restart --detector` |
| Page loads, pill "Disconnected" | rosbridge :9090 not up yet, or wrong address in the Drone field | wait a minute after power-on; drone: `systemctl status technic`; check the address |
| `get_telemetry failing` in the command log | SKYRIS stack not ready | `systemctl status technic`; `journalctl -u technic -n 50` |
| Detector pill "off" | detector not started or no model | drone: `~/airael/airael.sh logs detector`; check the model file `~/airael/models/fire-rgb-rk3588.rknn` |
| Detector running but on the wrong camera, or settings come back after a restart (D8) | a detector started by hand is still running (it respawns) | drone: `~/airael/airael.sh stop; pkill -f "roslaunch yolo_face fire_detector"; sleep 2; pkill -f fire_detector_node.py`, then `~/airael/airael.sh start --detector`; check `rosparam get /fire_detector/input_topic` |
| Detector FPS low or NPU busy | SKYRIS `rknn_face` demo still running (it restarts with `technic.service`) | `rosnode kill /rknn_face` (airael.sh does this on start) |
| No objects on the map although boxes are drawn | drone too low or tilted ("rays missed the floor", D10), or no marker pose yet | drone: `~/airael/airael.sh logs geoloc`; hold at least 1 m above the objects with markers in view |
| Take-off or Fly to target rejected | flight controller not ready, not in the field, or a field `/navigate` does not accept (D6) | read the reason in the command log; check position and mode |
| Camera picture frozen or "No stream" | camera topic not publishing, or web_video_server busy | try camera mode **JPEG** or **Snapshots**; drone: `rostopic hz /main_camera/image_raw` |
| SKYRIS camera compressors crash in a loop (D4) | compressed image transport missing | see D4 in the [defect log](module_B/defect_log.md); never run `apt --fix-broken install` |
| Event latency negative or huge | drone clock not set | checklist item 5 |
| SSH "Destination Host Unreachable" over Ethernet after a reboot | the drone lost its fixed address | connect over Wi-Fi and run, on the drone: `sudo nmcli con up laptop-eth` (the profile created in the deployment guide) |
| Dataset tab "dataset server offline" | dataset server not running | `~/airael/airael.sh status`; `~/airael/airael.sh logs dataset` |
| Route aborted: "pilot or failsafe took over" | flight mode left OFFBOARD (RC switch or failsafe) | intended behaviour; the pilot flies; restart the route when safe |

Logs of our services: `~/airael/logs/<name>.log` (`~/airael/airael.sh logs [gs|thermal|dataset|detector|geoloc]`).
SKYRIS logs: `journalctl -u technic`.
