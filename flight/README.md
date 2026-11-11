# flight

Autonomous navigation of the UAV.

**Covers:** R1 (autonomous route flight), R10 (return on operator command).

- Load a route from `missions/`
- Take off, follow waypoints, hold altitude suitable for thermal detection
- Listen for the operator's return command from the ground station and return home
- Publish drone pose (position, altitude, yaw) for `localization/`
