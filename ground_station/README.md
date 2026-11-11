# ground_station

Web interface for the operator.

**Covers:** R6 (receives coordinates), R7 (live map), R8 (event log), R10 (return command).

## Features
- Live map with detected objects: type and detection time on each marker
- Event table: timestamp, coordinates, object type, confidence
- Export log (CSV/JSON)
- Drone position on the map
- **Return home** button

Message format: see [`docs/architecture.md`](../docs/architecture.md#event-message).
