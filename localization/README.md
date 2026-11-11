# localization

Converts a detection in the image into ground coordinates.

**Covers:** R6 (coordinate error ≤ 0.5 m).

## Inputs
- Bounding-box centre (pixels)
- Camera intrinsics (focal length, principal point, distortion) — from calibration
- Camera mounting angle relative to the drone
- Drone position, altitude above ground, and attitude at the frame timestamp

## Method
Project the pixel ray through the camera model, rotate into the world frame using the drone
attitude, intersect with the ground plane, then convert the offset to map coordinates.

## Validation
Place markers at surveyed positions, fly over them, compare computed vs. true coordinates.
Record results in `docs/test-reports/`.
