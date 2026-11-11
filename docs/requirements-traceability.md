# Requirements Traceability

Each competition requirement, where it is implemented, and the evidence that it is met.
Update the **Status** and **Evidence** columns as work is done.

Status: ⬜ not started · 🟨 in progress · ✅ done · ❌ blocked

| ID | Requirement | Target | Module | Status | Evidence |
|---|---|---|---|---|---|
| R1 | Autonomous route flight | Completes route without pilot input | `flight/` | ⬜ | |
| R2 | Real-time thermal capture | Live thermograms onboard | `perception/` | ⬜ | |
| R3 | Flame detection | mAP@0.5 ≥ 85% | `perception/` | ⬜ | |
| R4 | Additional object | ≥ 1 extra class: _TBD_ | `perception/` | ⬜ | |
| R5 | Onboard inference speed | ≥ 10 FPS for > 90% of time | `perception/` | ⬜ | |
| R6 | Object coordinates | Error ≤ 0.5 m, sent to ground | `localization/` | ⬜ | |
| R7 | Live map | Type + timestamp shown | `ground_station/` | ⬜ | |
| R8 | Event log | ts, coords, type, confidence | `ground_station/` | ⬜ | |
| R9 | Demo detection | ≥ 1 flame detection per flight | whole system | ⬜ | |
| R10 | Return on command | Autonomous RTH | `flight/` | ⬜ | |
