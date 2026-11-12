"""Module C calculation workbook — reproduces the Module C report (ground-patrol baseline) with live formulas.

Sheets: Report · Model (8 cases side by side, each a full re-run) · Resources (bill of materials).
"""
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

OUT = "docs/Module_C_Economic_Model.xlsx"
F = "Arial"
BLUE, BLACK, GREEN = Font(name=F, color="0000FF"), Font(name=F), Font(name=F, color="008000")
BOLD, GREY = Font(name=F, bold=True), Font(name=F, color="595959")
TITLE = Font(name=F, bold=True, size=14)
HEAD = Font(name=F, bold=True, color="FFFFFF")
HFILL = PatternFill("solid", fgColor="1F2A36")
KEY = PatternFill("solid", fgColor="FFFF00")
SEC = PatternFill("solid", fgColor="E7EAEE")
thin = Side(style="thin", color="BFC5CC")
BOX = Border(top=thin, bottom=thin, left=thin, right=thin)
WRAP = Alignment(wrap_text=True, vertical="top")
USD = '$#,##0;-$#,##0;-'
USD2 = '$#,##0.00;-$#,##0.00;-'
PCT = '0.0%;-0.0%;-'
PCT0 = '0%;-0%;-'
NUM2 = '#,##0.00;-#,##0.00;-'
NUM1 = '#,##0.0;-#,##0.0;-'
INT = '#,##0;-#,##0;-'
YRS = '0.00 "yr"'

wb = Workbook()


def cell(ws, ref, value, font=BLACK, fmt=None, fill=None, wrap=False, border=True):
    c = ws[ref]
    c.value = value
    c.font = font
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if wrap:
        c.alignment = WRAP
    if border:
        c.border = BOX
    return c


def head(ws, row, labels):
    for i, lab in enumerate(labels, 1):
        c = ws.cell(row=row, column=i, value=lab)
        c.font, c.fill, c.border = HEAD, HFILL, BOX
        c.alignment = Alignment(wrap_text=True, vertical="center")


# =================================================================== Resources
rs = wb.create_sheet("Resources")
rs["A1"] = "Bill of resources (retail list prices, November 2026)"
rs["A1"].font = TITLE
for col, w in zip("ABCDEF", [8, 58, 7, 14, 14, 30]):
    rs.column_dimensions[col].width = w
head(rs, 3, ["Option", "Item", "Qty", "Unit price ($)", "Total ($)", "Source"])
bom_c = [
    ("Holybro X500 V2 ARF kit (frame, 4 motors, ESCs, props, power board)", 1, 329.00, "Holybro"),
    ("Pixhawk 6C flight controller with PM02 power module", 1, 217.99, "Holybro"),
    ("Holybro M10 GNSS module", 1, 49.99, "Holybro M10 listing"),
    ("Orange Pi 5 Pro 16 GB (RK3588S, 6 TOPS NPU)", 1, 447.19, "Newegg"),
    ("Mileseey TR256i thermal camera, 256 × 192", 1, 299.99, "Mileseey store"),
    ("Downward RGB camera, USB", 1, 40.00, "Assumption"),
    ("SiK telemetry radio V3, pair", 1, 58.99, "Holybro"),
    ("ELRS receiver", 1, 20.00, "Assumption"),
    ("Gens Ace 4S 5000 mAh LiPo", 5, 71.99, "BuddyRC"),
    ("4G LTE USB modem", 1, 60.00, "Assumption"),
    ("VL53L1X rangefinder, mounts, cables", 1, 80.00, "Assumption"),
]
kit_g = [("RadioMaster Pocket ELRS transmitter", 1, 69.99, "BuddyRC"),
         ("Multi-channel charger", 1, 150.00, "Assumption")]
kit_b = [("DJI Matrice 4T with remote controller (640 × 512 thermal, up to 49 min)", 1, 7199.00, "Drone Nerds"),
         ("Extra Matrice 4 series batteries (6 needed a day, 1 included)", 5, 244.00, "Dronefly"),
         ("Battery charging hub", 1, 150.00, "Assumption")]
r = 4
TOT = {}
for tag, label, items in [("C", "Option C, per aircraft", bom_c), ("C", "Option C, ground kit per operator", kit_g),
                          ("B", "Option B, per kit", kit_b)]:
    cell(rs, f"A{r}", label, BOLD, fill=SEC)
    for c_ in "BCDEF":
        rs[f"{c_}{r}"].fill = SEC
    r += 1
    first = r
    for name, q, p, src in items:
        cell(rs, f"A{r}", tag)
        cell(rs, f"B{r}", name, wrap=True)
        cell(rs, f"C{r}", q, BLUE, INT)
        cell(rs, f"D{r}", p, BLUE, USD2)
        cell(rs, f"E{r}", f"=C{r}*D{r}", BLACK, USD2)
        cell(rs, f"F{r}", src, wrap=True)
        r += 1
    cell(rs, f"B{r}", "Total", BOLD)
    cell(rs, f"E{r}", f"=SUM(E{first}:E{r-1})", BOLD, USD2)
    TOT[label] = f"Resources!$E${r}"
    r += 2

# =================================================================== Model
m = wb.create_sheet("Model")
m["A1"] = "Calculation model — every case is a full re-run of the same formulas"
m["A1"].font = TITLE
m["A2"] = ("Blue = input · green = taken from the Base column or another sheet · black = formula · yellow = what the "
           "case changes. Change a blue Base value and every case and the Report update.")
m["A2"].font = GREY
CASES = ["Base", "Pessimistic", "Optimistic", "Wages −30%", "Wages +30%", "Route 60 km/day", "Route 180 km/day",
         "Discount rate 10%"]
CC = [get_column_letter(3 + i) for i in range(len(CASES))]   # C..J
NOTE = get_column_letter(3 + len(CASES))                     # K
m.column_dimensions["A"].width = 46
m.column_dimensions["B"].width = 12
for c_ in CC:
    m.column_dimensions[c_].width = 14
m.column_dimensions[NOTE].width = 60
head(m, 4, ["Parameter / result", "Unit"] + CASES + ["Source, assumption or formula"])
m.freeze_panes = "C5"

R = {}
row = [5]


def section(title):
    cell(m, f"A{row[0]}", title, BOLD, fill=SEC)
    for c_ in ["B"] + CC + [NOTE]:
        m[f"{c_}{row[0]}"].fill = SEC
        m[f"{c_}{row[0]}"].border = BOX
    row[0] += 1


def inp(key, label, unit, base, fmt, note, over=None):
    rr = row[0]
    R[key] = rr
    cell(m, f"A{rr}", label)
    cell(m, f"B{rr}", unit, GREY)
    over = over or {}
    for i, c_ in enumerate(CC):
        if i == 0:
            is_formula = isinstance(base, str) and base.startswith("=")
            cell(m, f"{c_}{rr}", base, GREEN if is_formula else BLUE, fmt)
        elif CASES[i] in over:
            v = over[CASES[i]]
            if isinstance(v, str):
                v = v.replace("{row}", str(rr))
            cell(m, f"{c_}{rr}", v, BLUE, fmt, KEY)
        else:
            cell(m, f"{c_}{rr}", f"=$C{rr}", GREEN, fmt)
    cell(m, f"{NOTE}{rr}", note, GREY, wrap=True)
    row[0] += 1


def calc(key, label, unit, formula, fmt, note="", bold=False):
    rr = row[0]
    R[key] = rr
    cell(m, f"A{rr}", label, BOLD if bold else BLACK)
    cell(m, f"B{rr}", unit, GREY)
    for c_ in CC:
        f = formula.format(**{k: f"{c_}{v}" for k, v in R.items()})
        cell(m, f"{c_}{rr}", f, BOLD if bold else BLACK, fmt)
    cell(m, f"{NOTE}{rr}", note, GREY, wrap=True)
    row[0] += 1


section("Inputs: scope and money")
inp("L", "Patrol route inspected per day", "km/day", 120, INT, "Assumption: corridor network of one district",
    {"Route 60 km/day": 60, "Route 180 km/day": 180})
inp("D", "Fire-season operating days", "days/yr", 150, INT, "Assumption: May to September")
inp("H", "Assessment horizon", "years", 5, INT, "Agreed horizon")
inp("life", "Hardware life", "seasons", 3, INT, "Assumption: replaced once, in year 4")
inp("r", "Discount rate (real)", "%/yr", 0.013, PCT, "OMB Circular A-94, 2026 rates, 5-year real",
    {"Discount rate 10%": 0.10})
inp("w", "Field staff wage", "$/h", 24.94, USD2,
    "BLS OEWS, Forest and Conservation Technicians, May 2023 median",
    {"Wages −30%": "=$C{row}*0.7", "Wages +30%": "=$C{row}*1.3"})
inp("k", "Employer cost loading", "×", 1.30, NUM2, "Assumption: benefits and overheads")
inp("cv", "Vehicle cost, all-in", "$/mile", 0.76, USD2, "IRS standard mileage rate from 1 July 2026")
inp("mi", "Kilometres per mile", "km", 1.609344, '0.000000', "Definition")
inp("e", "Vehicle CO2", "g/mile", 400, INT, "US EPA")
section("Inputs: how each option works")
inp("va", "Ground patrol speed incl. stops", "km/h", 20, INT, "Assumption")
inp("na", "Ground patrol crew", "people", 2, INT, "Assumption: two-person crew for safety")
inp("o", "Daily overhead or set-up, every option", "h/day", 1, NUM1, "Assumption")
inp("a", "Access driving to the launch site, every option", "km/day", 40, INT, "Assumption")
inp("v", "Drone cruise speed", "km/h", 36, INT, "Assumption: 10 m/s")
inp("tB", "Usable flight per battery, Matrice 4T", "min", 35, INT, "Drone Nerds: plan 35–40 of the 49 min rated")
inp("tC", "Usable flight per battery, our aircraft", "min", 20, INT,
    "Assumption for an X500-class aircraft with payload", {"Pessimistic": 15})
inp("s", "Battery swap and relaunch", "min", 10, INT, "Assumption")
inp("N", "Our aircraft per operator", "aircraft", 2, INT, "Design choice", {"Optimistic": 3})
inp("crew", "People per drone operation (B and C)", "people", 1, INT,
    "1 with beyond-line-of-sight approval; pessimistic: line of sight only, a second person is needed",
    {"Pessimistic": 2})
section("Inputs: costs")
inp("P", "Our aircraft parts", "$/aircraft", "=" + TOT["Option C, per aircraft"], USD2, "Resources sheet")
inp("hwmult", "Our hardware price factor", "×", 1.0, NUM2, "Pessimistic: our hardware costs 30% more",
    {"Pessimistic": 1.3})
inp("spare", "Spares share", "% of aircraft", 0.10, PCT0, "Assumption")
inp("G", "Ground kit per operator", "$", "=" + TOT["Option C, ground kit per operator"], USD2, "Resources sheet")
inp("kitB", "Commercial drone kit (Option B)", "$", "=" + TOT["Option B, per kit"], USD2, "Resources sheet")
inp("devh", "Development and integration effort", "person-h", 640, INT, "Assumption: two engineers for 8 weeks")
inp("devr", "Engineering rate", "$/h", 40, USD2, "Assumption")
inp("share", "Districts sharing the development", "districts", 1, INT,
    "Optimistic: one software build serves 5 districts", {"Optimistic": 5})
inp("appr", "Approval and operator training (B and C)", "$", 2000, USD, "Assumption, same for B and C")
inp("m", "Maintenance and repairs", "% of hw/yr", 0.10, PCT0, "Assumption")
inp("ins", "Insurance", "$/aircraft/yr", 600, USD, "Assumption")
inp("data", "LTE data", "$/aircraft/month", 10, USD, "Assumption")
inp("host", "Cloud hosting", "$/month", 10, USD, "Assumption")

section("Person-hours per day")
calc("wl", "Loaded labour cost", "$/h", "={w}*{k}", USD2, "w × k")
calc("phA", "A. Ground patrol", "person-h", "={na}*({L}/{va}+{o})", NUM2, "na × (L ÷ va + o)")
calc("fB", "B. Flight time per day", "min", "={L}/{v}*60", NUM1, "L ÷ v")
calc("swB", "B. Battery swaps per day", "swaps", "=ROUNDUP({fB}/{tB},0)-1", INT, "batteries needed − 1")
calc("phB", "B. Commercial drone", "person-h", "={crew}*({fB}/60+{swB}*{s}/60+{o})", NUM2,
     "crew × (flight + swaps × s + o)")
calc("fC", "C. Flight time per aircraft per day", "min", "={L}/{N}/{v}*60", NUM1, "route split over N aircraft")
calc("swC", "C. Battery swaps per day, all aircraft", "swaps", "={N}*(ROUNDUP({fC}/{tC},0)-1)", INT,
     "N × (batteries per aircraft − 1); one operator does them one after another (conservative)")
calc("phC", "C. Our system", "person-h", "={crew}*({fC}/60+{swC}*{s}/60+{o})", NUM2, "crew × (flight + swaps × s + o)")

section("Capital cost (one-time, year 0)")
calc("hwB", "B. Hardware", "$", "={kitB}", USD)
calc("hwC", "C. Hardware: N aircraft + spares + ground kit", "$", "=({N}*{P}*(1+{spare})+{G})*{hwmult}", USD,
     "(N × P × (1 + spares) + G) × price factor")
calc("devC", "C. Development (this district's share)", "$", "={devh}*{devr}/{share}", USD)
calc("capA", "A. Capital cost", "$", "=0", USD, "Vehicle the service already owns")
calc("capB", "B. Capital cost", "$", "={hwB}+{appr}", USD)
calc("capC", "C. Capital cost", "$", "={hwC}+{devC}+{appr}", USD, bold=True)

section("Operating cost per year")
calc("opA", "A. Ground patrol", "$/yr", "={phA}*{wl}*{D}+({L}+{a})/{mi}*{cv}*{D}", USD,
     "labour + vehicle for route and access")
calc("labB", "B. Labour", "$/yr", "={phB}*{wl}*{D}", USD)
calc("opB", "B. Commercial drone", "$/yr", "={labB}+{a}/{mi}*{cv}*{D}+{m}*{hwB}+{ins}", USD,
     "labour + access driving + maintenance + insurance")
calc("labC", "C. Labour", "$/yr", "={phC}*{wl}*{D}", USD)
calc("vehC", "C. Vehicle (access only)", "$/yr", "={a}/{mi}*{cv}*{D}", USD)
calc("othC", "C. Maintenance, insurance, data, hosting", "$/yr",
     "={m}*{hwC}+{ins}*{N}+12*({data}*{N}+{host})", USD)
calc("opC", "C. Our system", "$/yr", "={labC}+{vehC}+{othC}", USD, bold=True)

section("Five-year cost of ownership (present value, same scope for every option)")
calc("AF", "Annuity factor", "×", "=(1-(1+{r})^-{H})/{r}", '0.0000', "(1 − (1 + r)^−H) ÷ r")
calc("ry", "Replacement year", "year", "={life}+1", INT)
calc("pvA", "A. 5-year cost", "$", "={capA}+{opA}*{AF}", USD)
calc("pvB", "B. 5-year cost", "$", "={capB}+{opB}*{AF}+IF({ry}<={H},{hwB}/(1+{r})^{ry},0)", USD,
     "capital + operating × annuity factor + discounted replacement")
calc("pvC", "C. 5-year cost", "$", "={capC}+{opC}*{AF}+IF({ry}<={H},{hwC}/(1+{r})^{ry},0)", USD, bold=True)
calc("km", "Route inspected over the horizon", "km", "={L}*{D}*{H}", INT)
calc("ckA", "A. Cost per km", "$/km", "={pvA}/{km}", USD2)
calc("ckB", "B. Cost per km", "$/km", "={pvB}/{km}", USD2)
calc("ckC", "C. Cost per km", "$/km", "={pvC}/{km}", USD2)
calc("svA", "Saving of C vs A (5-year)", "$", "={pvA}-{pvC}", USD, "equals the NPV of choosing C instead of A", True)
calc("svAp", "Saving of C vs A", "%", "={svA}/{pvA}", PCT0)
calc("svB", "Saving of C vs B (5-year)", "$", "={pvB}-{pvC}", USD, "equals the NPV of choosing C instead of B", True)
calc("svBp", "Saving of C vs B", "%", "={svB}/{pvB}", PCT0)


def comparison(tag, capR, opR, hwR, name):
    section(f"Cash flow of choosing our system instead of {name}")
    calc(f"f0{tag}", "Year 0: extra investment", "$", ("={" + capR + "}-{capC}") if capR else "=-{capC}", USD)
    for t in range(1, 6):
        rep = ("+IF({ry}=" + str(t) + ",{" + hwR + "}-{hwC},0)") if hwR else ("+IF({ry}=" + str(t) + ",-{hwC},0)")
        calc(f"f{t}{tag}", f"Year {t}: operating saving ± replacement", "$",
             "=IF(" + str(t) + "<={H},{" + opR + "}-{opC}" + rep + ",0)", USD)
    calc(f"c0{tag}", "Cumulative, year 0", "$", "={f0" + tag + "}", USD)
    for t in range(1, 6):
        calc(f"c{t}{tag}", f"Cumulative, year {t}", "$", "={c" + str(t - 1) + tag + "}+{f" + str(t) + tag + "}", USD)
    pb = '"not within 5 years"'
    for t in range(5, 0, -1):
        pb = ("IF({c" + str(t) + tag + "}>=0," + str(t - 1) + "+(-{c" + str(t - 1) + tag + "})/{f" + str(t) + tag
              + "}," + pb + ")")
    calc(f"pb{tag}", f"Payback vs {tag}", "years", "=IF({c0" + tag + "}>=0,0," + pb + ")", YRS,
         "year before break-even + shortfall ÷ that year's cash flow", True)
    calc(f"roi{tag}", f"ROI vs {tag} over the horizon", "%",
         "=SUM({f0" + tag + "}:{f5" + tag + "})/({capC}+IF({ry}<={H},{hwC},0))", PCT0,
         "net gain ÷ our total investment (capital + replacement)", True)
    calc(f"npv{tag}", f"NPV vs {tag}", "$", "=NPV({r},{f1" + tag + "}:{f5" + tag + "})+{f0" + tag + "}", USD,
         "Σ CFt ÷ (1 + r)^t; equals the saving in 5-year cost", True)
    calc(f"irr{tag}", f"IRR vs {tag}", "%", "=IFERROR(IRR({f0" + tag + "}:{f5" + tag + "}),\"n/a\")", PCT0,
         "rate at which NPV = 0", True)
    calc(f"sav{tag}", f"Net operating saving per year vs {tag}", "$/yr", "={" + opR + "}-{opC}", USD)


comparison("A", None, "opA", None, "ground patrol (A)")
comparison("B", "capB", "opB", "hwB", "the commercial drone (B)")

section("Social and environmental effects (per year, vs ground patrol)")
calc("hrs", "Field staff hours out of fire-risk terrain", "h/yr", "=({phA}-{phC})*{D}", INT)
calc("vkm", "Vehicle kilometres avoided", "km/yr", "=(({L}+{a})-{a})*{D}", INT)
calc("co2", "CO2 avoided", "t/yr", "={vkm}/{mi}*{e}/1000000", NUM1)

# =================================================================== Report
rp = wb.active
rp.title = "Report"
for col, w in zip("ABCDEF", [5, 40, 24, 24, 26, 26]):
    rp.column_dimensions[col].width = w


def B(key):
    return f"=Model!$C${R[key]}"


rp["A1"] = "Module C — Economic feasibility (Team Brics, Case 1: autonomous forest fire monitoring)"
rp["A1"].font = TITLE
rp["A2"] = ("Base case. Every figure is a formula on the Model sheet; inputs and sources are on Model and Resources. "
            "Scope: one district, 120 km of route a day, 150 fire-season days, 5 years, constant 2026 USD.")
rp["A2"].font = GREY
r = 4
rp.cell(row=r, column=1, value="1. Options compared on the same scope").font = BOLD
r += 1
head(rp, r, ["", "Characteristic", "A. Ground patrol (baseline)", "B. Commercial thermal drone", "C. Our system"])
rows = [("People in the field", B("na"), B("crew"), B("crew"), INT),
        ("Person-hours per day", B("phA"), B("phB"), B("phC"), NUM1),
        ("Capital cost ($)", B("capA"), B("capB"), B("capC"), USD),
        ("Operating cost per year ($)", B("opA"), B("opB"), B("opC"), USD),
        ("5-year cost, present value ($)", B("pvA"), B("pvB"), B("pvC"), USD),
        ("Cost per km inspected ($)", B("ckA"), B("ckB"), B("ckC"), USD2),
        ("How a fire is found", "Crew looks out of the vehicle", "Pilot watches a 640 × 512 thermal feed",
         "YOLO on the onboard NPU flags it and sends coordinates", None)]
for lab, a_, b_, c_, fmt in rows:
    r += 1
    cell(rp, f"B{r}", lab)
    for col, v in zip("CDE", (a_, b_, c_)):
        cell(rp, f"{col}{r}", v, GREEN if str(v).startswith("=") else BLACK, fmt, wrap=fmt is None)
r += 2
rp.cell(row=r, column=1, value="2. Cost-and-benefit table (our system, per district)").font = BOLD
r += 1
head(rp, r, ["No.", "Cost / benefit item", "Amount / metric", "Unit", "Comments", ""])
cb = [("Development costs", B("devC"), "$, one-time", "Software, integration and field testing, 640 person-hours"),
      ("Hardware", B("hwC"), "$, one-time; again in year 4", "2 aircraft, 10% spares, ground kit (Resources)"),
      ("Approval and training", B("appr"), "$, one-time", "Same for the commercial drone"),
      ("Operating costs", B("opC"), "$/yr", "Labour, access driving, maintenance, insurance, data, hosting"),
      ("Resource savings vs ground patrol", B("savA"), "$/yr", "Mostly labour and vehicle use"),
      ("Resource savings vs commercial drone", B("savB"), "$/yr", "Fewer operator hours; cheaper hardware to maintain"),
      ("Staff hours kept out of fire-risk terrain", B("hrs"), "h/yr", "Not converted to money"),
      ("Vehicle CO2 avoided", B("co2"), "t/yr", "Not converted to money")]
for i, (lab, v, unit, com) in enumerate(cb, 1):
    r += 1
    cell(rp, f"A{r}", i, BLACK, INT)
    cell(rp, f"B{r}", lab, wrap=True)
    cell(rp, f"C{r}", v, GREEN, NUM1 if unit.startswith("t") else (INT if unit.startswith("h") else USD))
    cell(rp, f"D{r}", unit, GREY, wrap=True)
    cell(rp, f"E{r}", com, wrap=True)
    rp.merge_cells(f"E{r}:F{r}")
r += 2
rp.cell(row=r, column=1, value="3. Economic efficiency indicators (5 years)").font = BOLD
r += 1
head(rp, r, ["", "Indicator", "Our system vs ground patrol", "Our system vs commercial drone"])
ind = [("Investment in year 0 ($)", f"=-Model!$C${R['f0A']}", f"=-Model!$C${R['f0B']}", USD),
       ("Net operating saving per year ($)", B("savA"), B("savB"), USD),
       ("Payback period", B("pbA"), B("pbB"), YRS),
       ("ROI over 5 years", B("roiA"), B("roiB"), PCT0),
       ("NPV at the real discount rate ($)", B("npvA"), B("npvB"), USD),
       ("IRR", B("irrA"), B("irrB"), PCT0),
       ("Saving in 5-year cost", B("svAp"), B("svBp"), PCT0)]
for lab, a_, b_, fmt in ind:
    r += 1
    cell(rp, f"B{r}", lab)
    cell(rp, f"C{r}", a_, GREEN, fmt, KEY)
    cell(rp, f"D{r}", b_, GREEN, fmt)
r += 2
rp.cell(row=r, column=1, value="4. Risk and uncertainty: each case is a full re-run (Model sheet)").font = BOLD
r += 1
head(rp, r, ["", "Case", "Payback vs ground patrol", "NPV vs ground patrol", "Payback vs commercial drone",
             "NPV vs commercial drone"])
for i, name in enumerate(CASES):
    r += 1
    c_ = CC[i]
    cell(rp, f"B{r}", name)
    cell(rp, f"C{r}", f"=Model!{c_}{R['pbA']}", GREEN, YRS)
    cell(rp, f"D{r}", f"=Model!{c_}{R['npvA']}", GREEN, USD)
    cell(rp, f"E{r}", f"=Model!{c_}{R['pbB']}", GREEN, YRS)
    cell(rp, f"F{r}", f"=Model!{c_}{R['npvB']}", GREEN, USD)
r += 2
rp.cell(row=r, column=1, value="5. Conclusion").font = BOLD
r += 1
cell(rp, f"B{r}",
     f'=IF(AND(ISNUMBER(Model!$C${R["pbA"]}),Model!$C${R["npvA"]}>0),"Economically feasible","Not economically feasible")'
     f'&": against ground patrols our system saves "&TEXT(Model!$C${R["svAp"]},"0%")&" of the 5-year cost ("'
     f'&TEXT(Model!$C${R["svA"]},"$#,##0")&" per district) and pays back in "&TEXT(Model!$C${R["pbA"]},"0.0")'
     f'&" years. Against a commercial thermal drone it is "&TEXT(Model!$C${R["svBp"]},"0%")&" cheaper; there its '
     f'advantage is automatic, logged detection rather than cost."', GREEN, wrap=True, border=False)
rp.merge_cells(f"B{r}:F{r}")
rp.row_dimensions[r].height = 48
r += 2
rp.cell(row=r, column=2, value="Sources").font = BOLD
for src in ["BLS OEWS, Forest and Conservation Technicians (May 2023 median wage)",
            "IRS standard mileage rate (from 1 July 2026) · US EPA vehicle CO2 per mile · OMB Circular A-94 (2026 real rate)",
            "Prices: Holybro, Newegg, Mileseey, BuddyRC, Drone Nerds, Dronefly (retail list prices, November 2026)",
            "Items marked 'Assumption' had no single verifiable listing; all are blue input cells."]:
    r += 1
    rp.cell(row=r, column=2, value=src).font = Font(name=F, size=9, color="595959")

for sh in wb.worksheets:
    sh.page_setup.orientation = "landscape"
    sh.sheet_properties.pageSetUpPr.fitToPage = True
    sh.page_setup.fitToWidth = 1
    sh.page_setup.fitToHeight = 0
wb.save(OUT)
print("saved", OUT)
