# Test Reports

One file per test flight or benchmark, named `YYYY-MM-DD-short-name.md`.

## Template

```markdown
# YYYY-MM-DD — <test name>

- **Location / conditions:**
- **Hardware & software version (git commit):**
- **Goal / requirement tested:** (R1–R10)

## Results
| Metric | Target | Measured |
|---|---|---|
| mAP@0.5 (flame) | ≥ 0.85 | |
| FPS ≥ 10 share of time | > 90% | |
| Coordinate error | ≤ 0.5 m | |
| Flame detections in flight | ≥ 1 | |

## Observations

## Logs / media
```
