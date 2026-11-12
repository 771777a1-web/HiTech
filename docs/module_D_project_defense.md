# Module D: project defence

The defence presentation is submitted separately in PPTX and PDF (`Team_Brics_Defense`). This page lists where
each claim in the deck is backed in this repository, and the slide corrections needed so the deck matches the
software that runs on the drone.

## Where the evidence is

| Slide | Claim | Backed by |
|-------|-------|-----------|
| 5 Architecture | sensing → onboard detection and localisation → ground station; PX4 under it | [architecture.md](architecture.md) |
| 10 Original contribution | localisation turns a box into x, y in metres | [`drone/fire_geoloc.py`](../drone/fire_geoloc.py), [`tests/test_geoloc.py`](../tests/test_geoloc.py) |
| 10 Dataset | 186 images | [evidence/2026-11-12_dataset_and_model.txt](../evidence/2026-11-12_dataset_and_model.txt): 186 RGB images, 333 boxes (campfire, tree), split by session |
| 11 Test results | thresholds and results | [module_B/test_plan.md](module_B/test_plan.md), [module_B/test_results.md](module_B/test_results.md) |
| 12 Abnormal conditions | pilot override, link loss | test plan, end-to-end section |
| 14 Limitations solved | no heat from the prop; no GPS indoors; thermal camera mount | [defect log](module_B/defect_log.md) D5; [architecture.md](architecture.md) |
| 15 Economics | payback 7 months, ROI 651 %, NPV $228.7k, IRR 170 % | [module_C_economic_feasibility.md](module_C_economic_feasibility.md), workbook |

## Corrections needed in the deck (TODO before the defence)

| Slide | Now says | Should say |
|-------|----------|------------|
| 6, 10, 12 | additional object = flag, and heated tree found by the thermal camera | additional object = **tree**, detected by the RGB model; heated-tree fusion was not implemented |
| 10 | "Code: firewatch/geometry.py" | "Code: drone/fire_geoloc.py" |
| 11, 12 | T1–T7 and M1–M3, "0.2 m", "confidence ≥ 0.45" | MC1–MC7 and FM1–FM3 with the thresholds in the test plan (mapping table at its end) |
| 13, 18 | `[github.com/…]`, `[link]` | the repository URL and the video link |
| 11–13 | "Pending" / placeholders | measured values from [test_results.md](module_B/test_results.md) after the flights; leave "not measured" where there is no record |
