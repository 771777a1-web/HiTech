# System Architecture

```
            ┌──────────────────────── UAV (onboard) ────────────────────────┐
            │                                                               │
 Thermal ──►│ perception: capture → YOLO on NPU ──► detections (bbox, cls,  │
 camera     │                                       confidence, frame ts)   │
            │                                             │                 │
 Flight  ◄─►│ flight: route follower, RTH        pose ───►│                 │
 controller │                                             ▼                 │
            │                         localization: bbox + pose → lat/lon   │
            └─────────────────────────────────────────────┬─────────────────┘
                                                          │ data link
                                                          ▼
                                ground_station: live map · event log · RTH button
```

## Data flow

1. **Capture** — thermal frames read onboard with a timestamp.
2. **Detect** — YOLO model (converted for the NPU) returns class, bounding box, confidence.
3. **Localize** — bbox centre + drone position/altitude/attitude + camera parameters → ground
   coordinates.
4. **Transmit** — event sent to the ground station.
5. **Display & log** — object drawn on the map; event appended to the log.
6. **Command** — operator can trigger return-to-home at any time.

## Event message

Every detection is sent and logged in this form (covers R6–R8):

```json
{
  "timestamp": "2026-11-11T10:15:42.318Z",
  "object_type": "campfire",
  "confidence": 0.93,
  "lat": 0.0,
  "lon": 0.0,
  "alt_m": 0.0,
  "drone": { "lat": 0.0, "lon": 0.0, "alt_m": 0.0, "yaw_deg": 0.0 },
  "frame_id": 1234
}
```
