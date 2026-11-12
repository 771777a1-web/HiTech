# Module C: economic feasibility (summary)

The full report is the submitted Module C document (11 Nov 2026). Every figure in it comes from the calculation
workbook [`docs/Module_C_Economic_Model.xlsx`](Module_C_Economic_Model.xlsx), which has live formulas and a
source for every input. The workbook can be rebuilt from [`tools/build_module_c_workbook.py`](../tools/build_module_c_workbook.py):

```bash
pip install openpyxl
python3 tools/build_module_c_workbook.py      # run from the repository root; writes docs/Module_C_Economic_Model.xlsx
```

The rebuilt file was compared cell by cell with the shipped one (no differences), and after recalculation in
LibreOffice its Report sheet gives the figures below (checked 12 Nov 2026).

**Conclusion: economically feasible.** One forest district, 120 km of patrol route a day, 150 fire-season days,
5 years, constant 2026 USD, real discount rate 1.3 %.

| | A. Ground patrol (baseline) | B. Commercial thermal drone | C. Our system |
|---|---|---|---|
| People in the field | 2 | 1 | 1 |
| Capital cost | $0 | $10,569 | $32,139 |
| Operating cost per year | $79,420 | $29,417 | $24,301 |
| 5-year cost, present value | $382,071 | $160,227 | $153,353 |
| Cost per km inspected | $4.25 | $1.78 | $1.70 |

| Indicator | Our system vs ground patrol | Our system vs commercial drone |
|-----------|-----------------------------|--------------------------------|
| Payback | 0.58 years | 3.68 years |
| ROI over 5 years | 651 % | 22 % |
| NPV at 1.3 % | $228,718 | $6,874 |
| IRR | 170 % | 11 % |
| Saving in 5-year cost | 60 % | 4 % |

Risk: eight cases are re-run in the workbook (pessimistic, optimistic, wages ±30 %, route 60 and 180 km/day,
discount rate 10 %). Against ground patrols every case pays back within 1.2 years; against the commercial drone
three cases do not pay back within 5 years.

Note: the BOM is for the outdoor deployment version (X500-class aircraft, Pixhawk 6C, GNSS), not the indoor
competition prototype. The savings assume the detector meets its Module B targets, which are not yet measured in flight.
