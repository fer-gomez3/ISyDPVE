"""Engineering workbook with live Excel formulas (openpyxl).

Sheets
  README / Inputs      editable inputs, colour-coded by origin (DOC / ASSUMPTION / INPUT NEEDED)
  Telemetry            sensor count x bits / interval -> rate per subsystem (formulas)
  Capacity             daily data vs downlink capacity, DSN time, required rate (formulas)
  HGA, Link, Power     antenna gain, X-band link budget, DC power / heat / energy (formulas)
  Satellites, Stations, Downlink Contacts, DSN Windows, Transfer by Subsystem, RF Trade Cases
                       numeric exports of the Python scenario results (static snapshots)

Empty required inputs show "INPUT NEEDED" instead of a number. Nothing is invented.
Origin colours: green = project documentation, yellow = preliminary assumption,
red = missing, blue = calculated.
"""
import csv
import json
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.workbook.defined_name import DefinedName
from .parameters import load as load_parameters

FILL = {"DOC": "C6EFCE", "ASSUMPTION": "FFEB9C", "INPUT NEEDED": "F8CBAD", "CALC": "DDEBF7"}
HEADER = PatternFill("solid", fgColor="17365D")


def _load(path):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _typed(v):
    if isinstance(v, str):
        if v in ("True", "False"):
            return v == "True"
        try:
            return float(v)
        except ValueError:
            return v
    return v


def _header(ws, row=1):
    for c in ws[row]:
        if c.value is not None:
            c.fill = HEADER
            c.font = Font(bold=True, color="FFFFFF")
            c.alignment = Alignment(wrap_text=True, vertical="top")


def _widths(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w


def _csv_sheet(wb, title, path):
    p = Path(path)
    if not p.exists():
        return
    ws = wb.create_sheet(title)
    with p.open(encoding="utf-8", newline="") as f:
        for i, row in enumerate(csv.reader(f)):
            ws.append(row if i == 0 else [_typed(x) if x != "" else None for x in row])
    _header(ws)
    ws.freeze_panes = "A2"
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 22


def export(output="outputs/SELENA_TTC_Model.xlsx", root=".", link_input="data/link_budget_inputs.json", out_dir=None):
    root = Path(root)
    tel_cfg = _load(root / "data/telemetry_generation_inputs.json")
    hga = _load(root / "data/hga_preliminary_design.json")
    link = _load(root / link_input)
    detailed = _load(root / "data/telemetry_detailed_scenario.json")
    params = load_parameters(root / "data/ttc_parameters.json")
    org = params["origins"]
    from .parameters import apply_policy
    pol = apply_policy(detailed.get("policy", {}), params)

    wb = Workbook()
    readme = wb.active
    readme.title = "README"
    for row in [
        ["SELENA TT&C / OBDH engineering workbook"],
        ["Edit cells on 'Inputs' and 'Telemetry' (blue font). Calculated cells are formulas; Excel recalculates on change."],
        ["Colours: green = project documentation, yellow = preliminary assumption, red = missing input, blue = calculated."],
        ["Scenario sheets (Satellites, Stations, Downlink Contacts, DSN Windows, Transfer by Subsystem, RF Trade Cases) are snapshots of the Python run: rerun main.py to refresh them."],
        ["Geometry is NOT validated 2030 propagation; DSN time is NOT booked. See 'Limitations'."],
    ]:
        readme.append(row)
    readme["A1"].font = Font(bold=True, size=14)
    readme.column_dimensions["A"].width = 140

    # ---------------- Inputs ----------------
    inp = wb.create_sheet("Inputs")
    inp.append(["Name", "Parameter", "Value", "Unit", "Origin", "Source"])
    names = {}

    def add(name, label, value, unit, origin, source):
        inp.append([name, label, value, unit, origin if value is not None else "INPUT NEEDED", source])
        r = inp.max_row
        names[name] = f"Inputs!$C${r}"
        inp.cell(r, 3).font = Font(color="0000FF")
        inp.cell(r, 5).fill = PatternFill("solid", fgColor=FILL[inp.cell(r, 5).value])

    add("n_sats", "Satellites in constellation", params["n_satellites"], "-", org["n_satellites"]["origin"], "ttc_parameters.json: " + org["n_satellites"]["source"])
    add("hga_d_m", "HGA diameter", hga.get("diameter_m"), "m", "ASSUMPTION", "hga_preliminary_design.json (380 mm, not selected hardware)")
    add("hga_eta", "HGA aperture efficiency", hga.get("aperture_efficiency"), "-", "ASSUMPTION", "hga_preliminary_design.json")
    add("freq_hz", "Downlink frequency (X-band)", hga.get("frequency_hz") or link.get("frequency_hz"), "Hz", "ASSUMPTION", "hga_preliminary_design.json")
    add("rate_bps", "Gross downlink rate", params["downlink_gross_bps"], "bit/s", org["downlink_gross_bps"]["origin"], "ttc_parameters.json: " + org["downlink_gross_bps"]["source"])
    add("overhead", "Protocol overhead fraction", params["protocol_overhead_fraction"], "-", org["protocol_overhead_fraction"]["origin"], "ttc_parameters.json: " + org["protocol_overhead_fraction"]["source"])
    add("setup_min", "Acquisition / setup time per contact", params["dsn_setup_minutes"], "min", org["dsn_setup_minutes"]["origin"], "ttc_parameters.json: " + org["dsn_setup_minutes"]["source"])
    add("min_useful_tx_min", "Minimum useful transmit time per contact", params["min_useful_tx_minutes"], "min", org["min_useful_tx_minutes"]["origin"], "ttc_parameters.json: " + org["min_useful_tx_minutes"]["source"])
    add("min_contact_min", "Minimum contact duration (setup + minimum useful transmit)", "=setup_min+min_useful_tx_min", "min", "CALC", "formula; always exceeds the setup time")
    add("net_hours_day", "DSN network hours per day (all satellites)", params["dsn_daily_network_hours"], "h/day", org["dsn_daily_network_hours"]["origin"], "ttc_parameters.json: " + org["dsn_daily_network_hours"]["source"])
    prio = {str(k): v for k, v in pol.get("priority_max_age_hours", {}).items()}
    dl = min([s.get("max_age_hours") or prio.get(str(s.get("priority"))) for s in detailed.get("streams", [])] or [None])
    add("min_deadline_h", "Tightest data-age deadline across streams", dl, "h", "ASSUMPTION", "priority policy (design policy, not a PDF requirement)")
    add("dist_km", "Earth-spacecraft distance", link.get("distance_km"), "km", "ASSUMPTION", "link_budget_inputs.json (needs real geometry)")
    add("gt_dbk", "DSN receive G/T", link.get("rx_gt_db_per_k"), "dB/K", "ASSUMPTION", "link_budget_inputs.json (verify against DSN 810-005)")
    add("ebn0_db", "Required Eb/N0", link.get("required_ebn0_db"), "dB", "ASSUMPTION", "link_budget_inputs.json (depends on modulation/FEC/BER)")
    add("loss_db", "Other losses (pointing, feed, polarization, atmosphere)", link.get("losses_db"), "dB", "ASSUMPTION", "link_budget_inputs.json")
    add("margin_db", "Design margin", link.get("margin_db"), "dB", "ASSUMPTION", "link_budget_inputs.json")
    add("rf_override_w", "Chosen TX RF power (blank = use minimum)", link.get("tx_rf_w"), "W", "ASSUMPTION", "link_budget_inputs.json")
    add("pa_eff", "Power amplifier efficiency", link.get("pa_efficiency"), "-", "ASSUMPTION", "link_budget_inputs.json")
    add("elec_w", "Transponder electronics power", link.get("electronics_w"), "W", "ASSUMPTION", "link_budget_inputs.json")
    add("standby_w", "Standby power", link.get("standby_w"), "W", "ASSUMPTION", "link_budget_inputs.json")
    add("c_ms", "Speed of light", 299792458, "m/s", "DOC", "constant")
    add("k_w", "Boltzmann constant", 1.380649e-23, "J/K", "DOC", "constant")
    _header(inp)
    _widths(inp, [16, 52, 16, 9, 14, 70])
    inp.freeze_panes = "A2"
    for n, ref in names.items():
        wb.defined_names[n] = DefinedName(n, attr_text=ref)

    # ---------------- Telemetry ----------------
    tl = wb.create_sheet("Telemetry")
    tl.append(["Subsystem", "Component", "Count", "Bits / sample", "Interval s", "Rate bit/s", "Origin", "Source"])
    for s in tel_cfg.get("subsystems", []):
        origin = "DOC" if s["source_type"] == "PDF" else "ASSUMPTION"
        comps = s.get("components") or []
        if s.get("pdf_rate_bps") is not None and not comps:
            tl.append([s["name"], "aggregate rate from documentation", None, None, None, s["pdf_rate_bps"], origin, s["source"]])
            r = tl.max_row
            tl.cell(r, 6).font = Font(color="0000FF")
        for c in comps:
            tl.append([s["name"], c["name"], c["count"], c["bits_per_sample"], c["interval_seconds"], None, origin, s["source"]])
            r = tl.max_row
            tl.cell(r, 6).value = f"=C{r}*D{r}/E{r}"
            for col in (3, 4, 5):
                tl.cell(r, col).font = Font(color="0000FF")
        for r in range(tl.max_row - max(len(comps), 1) + 1, tl.max_row + 1):
            tl.cell(r, 7).fill = PatternFill("solid", fgColor=FILL[origin])
    last = tl.max_row
    tl.append([])
    tl.append(["Summary per subsystem", None, None, None, None, "Rate bit/s", "Mbit/day", "MB/day",
               "PDF reference bit/s (DOC)", "Calculated - PDF bit/s", "Status"])
    hdr = tl.max_row
    for c in tl[hdr]:
        if c.value:
            c.font = Font(bold=True)
            c.alignment = Alignment(wrap_text=True, vertical="top")
    first_sum = hdr + 1
    for s in tel_cfg.get("subsystems", []):
        tl.append([s["name"]])
        r = tl.max_row
        tl.cell(r, 6).value = f"=SUMIF($A$2:$A${last},A{r},$F$2:$F${last})"
        tl.cell(r, 7).value = f"=F{r}*86400/1000000"
        tl.cell(r, 8).value = f"=F{r}*86400/8000000"
        ref = s.get("pdf_rate_bps")
        if ref is not None:
            tl.cell(r, 9).value = ref
            tl.cell(r, 9).fill = PatternFill("solid", fgColor=FILL["DOC"])
            tl.cell(r, 10).value = f"=F{r}-I{r}"
        pending = s["source_type"] != "PDF"
        head = (f'IF(ISNUMBER(I{r}),IF(ABS(J{r})<0.000000001,"Matches PDF aggregate'
                + (' by construction - NOT independent verification"' if str(s["source_type"]).startswith("REVERSE_ENGINEERED") else '"')
                + ',"DIFFERS from PDF aggregate - investigate"),"No PDF reference")')
        tl.cell(r, 11).value = f'={head}&" | PENDING REAL DATA"' if pending else f'={head}'
    last_sum = tl.max_row
    tl.append(["TOTAL per satellite"])
    r = tl.max_row
    tl.cell(r, 6).value = f"=SUM(F{first_sum}:F{last_sum})"
    tl.cell(r, 7).value = f"=F{r}*86400/1000000"
    tl.cell(r, 8).value = f"=F{r}*86400/8000000"
    tot_row = r
    for c in tl[r]:
        c.font = Font(bold=True)
    tl.append(["TOTAL, all satellites"])
    r = tl.max_row
    tl.cell(r, 6).value = f"=F{tot_row}*n_sats"
    tl.cell(r, 7).value = f"=G{tot_row}*n_sats"
    tl.cell(r, 8).value = f"=H{tot_row}*n_sats"
    for rr in range(first_sum, tl.max_row + 1):
        for col in (6, 7, 8):
            tl.cell(rr, col).fill = PatternFill("solid", fgColor=FILL["CALC"])
            tl.cell(rr, col).number_format = "#,##0.00"
    _header(tl)
    _widths(tl, [26, 36, 10, 14, 12, 14, 14, 52, 20, 18, 70])
    wb.defined_names["tel_total_bps"] = DefinedName("tel_total_bps", attr_text=f"Telemetry!$F${tot_row}")
    wb.defined_names["tel_mbit_day"] = DefinedName("tel_mbit_day", attr_text=f"Telemetry!$G${tot_row}")

    # ---------------- HGA ----------------
    ha = wb.create_sheet("HGA")
    ha.append(["Quantity", "Value", "Unit", "Formula / note"])
    rows = [
        ("Wavelength", "=c_ms/freq_hz", "m", "c / f"),
        ("Idealized gain (linear)", "=hga_eta*(PI()*hga_d_m/B2)^2", "-", "eta (pi D / lambda)^2"),
        ("Idealized gain", "=10*LOG10(B3)", "dBi", "no pointing, feed or polarization loss"),
        ("Half-power beamwidth (approx.)", "=70*B2/hga_d_m", "deg", "70 lambda / D"),
        ("Diameter needed for the minimum-RF design gain", '=IF(ISNUMBER(Link!B9),c_ms/(PI()*freq_hz)*SQRT(10^(Link!B9/10)/hga_eta),"INPUT NEEDED")', "m", "see Link sheet: gain at which RF power equals chosen RF power"),
    ]
    for r in rows:
        ha.append(list(r))
    for rr in range(2, ha.max_row + 1):
        ha.cell(rr, 2).fill = PatternFill("solid", fgColor=FILL["CALC"])
    _header(ha)
    _widths(ha, [48, 18, 8, 64])
    wb.defined_names["hga_gain_dbi"] = DefinedName("hga_gain_dbi", attr_text="HGA!$B$4")

    # ---------------- Capacity ----------------
    cp = wb.create_sheet("Capacity")
    cp.append(["Quantity", "Value", "Unit", "Formula / note"])
    cap_rows = [
        ("Net data rate after protocol overhead", "=rate_bps*(1-overhead)", "bit/s", "gross rate x (1 - overhead)"),
        ("Telemetry generated per satellite per day", "=tel_mbit_day", "Mbit/day", "from Telemetry sheet"),
        ("Link duty cycle needed", "=tel_total_bps/B2", "-", "mean generation rate / net rate"),
        ("Transmit time per satellite per day (1 contact)", "=B3*1000000/B2/60", "min", "daily data / net rate"),
        ("Contact time per satellite per day incl. setup", "=B5+setup_min", "min", "transmit + setup"),
        ("DSN network time, all satellites, 1 contact/day each", "=n_sats*B6/60", "h/day", ""),
        ("Fits in assumed DSN network hours?", '=IF(B7<=net_hours_day,"OK","EXCEEDS ASSUMED DSN HOURS")', "-", "compare with Inputs: net_hours_day"),
        ("Required net rate to fit 1 contact/day each in assumed DSN hours", '=IF(net_hours_day*60/n_sats>setup_min,B3*1000000/((net_hours_day*60/n_sats-setup_min)*60),"setup consumes all time")', "bit/s", "daily data / (hours per satellite - setup)"),
        ("Required gross rate for that case", '=IF(ISNUMBER(B9),B9/(1-overhead),B9)', "bit/s", "net / (1 - overhead)"),
        ("Contacts per day per satellite to meet tightest deadline", "=IF(ISNUMBER(min_deadline_h),24/min_deadline_h,\"INPUT NEEDED\")", "1/day", "24 h / tightest max data age"),
        ("Transmit time per such contact", '=IF(ISNUMBER(min_deadline_h),tel_total_bps*min_deadline_h*3600/B2/60,"INPUT NEEDED")', "min", "data produced in one deadline period / net rate"),
        ("DSN network time to meet that deadline, all satellites", '=IF(ISNUMBER(B11),n_sats*B11*(B12+setup_min)/60,"INPUT NEEDED")', "h/day", "n x contacts x (tx + setup)"),
        ("Fits in assumed DSN network hours?", '=IF(ISNUMBER(B13),IF(B13<=net_hours_day,"OK","EXCEEDS ASSUMED DSN HOURS"),B13)', "-", ""),
        ("Contact with min duration: useful transmit time", "=min_contact_min-setup_min", "min", "zero or negative means such a contact carries no data"),
    ]
    for r in cap_rows:
        cp.append(list(r))
    for rr in range(2, cp.max_row + 1):
        cp.cell(rr, 2).fill = PatternFill("solid", fgColor=FILL["CALC"])
        cp.cell(rr, 2).number_format = "#,##0.00"
    _header(cp)
    _widths(cp, [62, 22, 10, 56])

    # ---------------- Link ----------------
    lk = wb.create_sheet("Link")
    lk.append(["Quantity", "Value", "Unit", "Formula / note"])

    def guard(expr, extra=""):
        cond = "AND(COUNT(dist_km,freq_hz,rate_bps,ebn0_db,loss_db,margin_db,gt_dbk)=7" + (f",{extra}" if extra else "") + ")"
        return f'=IF({cond},{expr},"INPUT NEEDED")'

    lk_rows = [
        ("Free-space path loss", guard("20*LOG10(4*PI()*dist_km*1000*freq_hz/c_ms)"), "dB", "20 log10(4 pi d f / c)"),
        ("Required EIRP incl. margin", guard("ebn0_db+margin_db+10*LOG10(rate_bps)+B2+loss_db-gt_dbk+10*LOG10(k_w)"), "dBW", "Eb/N0 + margin + 10log R + FSPL + L - G/T + 10log k"),
        ("Antenna gain used", "=hga_gain_dbi", "dBi", "HGA sheet (change diameter on Inputs)"),
        ("Minimum RF power incl. margin", guard("10^((B3-B4)/10)"), "W", "EIRP - G"),
        ("Chosen RF power", '=IF(ISNUMBER(B5),IF(ISNUMBER(rf_override_w),rf_override_w,B5),"INPUT NEEDED")', "W", "override on Inputs, else minimum"),
        ("Available Eb/N0", guard("10*LOG10(B6)+B4-B2-loss_db+gt_dbk-10*LOG10(k_w)-10*LOG10(rate_bps)"), "dB", ""),
        ("Achieved margin over required Eb/N0", '=IF(ISNUMBER(B7),B7-ebn0_db,"INPUT NEEDED")', "dB", "equals design margin when RF = minimum"),
        ("Antenna gain at which RF = chosen RF", '=IF(ISNUMBER(B5),B4+10*LOG10(B5/B6),"INPUT NEEDED")', "dBi", "used by HGA sheet"),
    ]
    for r in lk_rows:
        lk.append(list(r))
    for rr in range(2, lk.max_row + 1):
        lk.cell(rr, 2).fill = PatternFill("solid", fgColor=FILL["CALC"])
        lk.cell(rr, 2).number_format = "#,##0.000"
    _header(lk)
    _widths(lk, [44, 22, 8, 64])

    # ---------------- Power ----------------
    pw = wb.create_sheet("Power")
    pw.append(["Quantity", "Value", "Unit", "Formula / note"])
    pw_rows = [
        ("RF output power", "=Link!B6", "W", "Link sheet"),
        ("Transmitter DC power", '=IF(AND(ISNUMBER(B2),COUNT(pa_eff,elec_w)=2),B2/pa_eff+elec_w,"INPUT NEEDED")', "W", "RF / efficiency + electronics"),
        ("Dissipated heat during transmission", '=IF(ISNUMBER(B3),B3-B2,"INPUT NEEDED")', "W", "DC - RF"),
        ("Standby power", '=IF(ISNUMBER(standby_w),standby_w,"INPUT NEEDED")', "W", ""),
        ("Transmit time per satellite per day", "=Capacity!B5/60", "h", "Capacity sheet (1 contact/day)"),
        ("Transmit energy per day", '=IF(ISNUMBER(B3),B3*B6,"INPUT NEEDED")', "Wh", "DC x transmit time"),
        ("Standby energy per day", '=IF(ISNUMBER(B5),B5*(24-B6),"INPUT NEEDED")', "Wh", "standby x remaining time"),
        ("Mean TT&C electrical power", '=IF(AND(ISNUMBER(B7),ISNUMBER(B8)),(B7+B8)/24,"INPUT NEEDED")', "W", "(transmit + standby) / 24 h"),
    ]
    for r in pw_rows:
        pw.append(list(r))
    for rr in range(2, pw.max_row + 1):
        pw.cell(rr, 2).fill = PatternFill("solid", fgColor=FILL["CALC"])
        pw.cell(rr, 2).number_format = "#,##0.000"
    _header(pw)
    _widths(pw, [44, 22, 8, 56])

    # ---------------- Scenario snapshots (typed numbers) ----------------
    out = Path(out_dir) if out_dir else root / "outputs"
    sim = _load(out / "downlink_simulation.json")
    if sim.get("satellites"):
        _csv_sheet(wb, "Satellites", out / "per_satellite_summary.csv")
        if "Satellites" in wb.sheetnames:
            ss = wb["Satellites"]
            head = [c.value for c in ss[1]]
            bal = len(head) + 1
            ss.cell(1, bal, "balance_mbit (generated - downloaded - remaining; must be 0)")
            g, d, r = (head.index(k) + 1 for k in ("generated_mbit", "downloaded_mbit", "remaining_mbit"))
            for row in range(2, ss.max_row + 1):
                L = ss.cell(row, 1).column_letter
                ss.cell(row, bal).value = f"={ss.cell(row, g).column_letter}{row}-{ss.cell(row, d).column_letter}{row}-{ss.cell(row, r).column_letter}{row}"
                ss.cell(row, bal).fill = PatternFill("solid", fgColor=FILL["CALC"])
            _header(ss)
            sat_rows = ss.max_row
            bal_letter = ss.cell(1, bal).column_letter
        st = wb.create_sheet("Stations")
        st.append(["Station", "Contacts", "Useful hours", "Capacity Mbit", "Downloaded Mbit"])
        for station in sorted({c["station"] for c in sim["contacts"]}):
            mine = [c for c in sim["contacts"] if c["station"] == station]
            st.append([station, len(mine), sum(c["useful_seconds"] for c in mine) / 3600,
                       sum(c["capacity_mbit"] for c in mine), sum(c["downloaded_mbit"] for c in mine)])
        _header(st)
        _widths(st, [16, 12, 14, 16, 16])
    for title, fname in [("Downlink Contacts", "downlink_contacts.csv"), ("DSN Windows", "dsn_allocated_windows.csv"),
                         ("Transfer by Subsystem", "transfer_by_subsystem.csv")]:
        _csv_sheet(wb, title, out / fname)
    trade = _load(out / "xband_trade_study.json")
    if trade.get("cases"):
        tr = wb.create_sheet("RF Trade Cases")
        tr.append(["Status: " + trade.get("status", ""), "All inputs are assumptions, not verified hardware"])
        tr.append(["distance_km", "rx_gt_db_per_k", "tx_gain_dbi", "data_rate_bps", "fspl_db", "min_tx_rf_w", "est_tx_dc_w", "est_heat_w"])
        for c in trade["cases"]:
            i = c["inputs"]
            tr.append([i["distance_km"], i["rx_gt_db_per_k"], i["tx_gain_dbi"], i["data_rate_bps"], c["free_space_path_loss_db"],
                       c["minimum_tx_rf_w_with_design_margin"], c["estimated_tx_dc_w"], c["estimated_dissipated_heat_w"]])
        _header(tr, 2)
        tr.freeze_panes = "A3"
        tr.auto_filter.ref = f"A2:H{tr.max_row}"
        _widths(tr, [14, 16, 14, 16, 12, 14, 14, 14])

    alloc = _load(out / "dsn_allocation_summary.json")
    if alloc:
        da = wb.create_sheet("DSN Allocation")
        da.append(["Quantity", "Value", "Unit / note"])
        for k, u in [("status", ""), ("daily_network_hours_limit", "h/day, shared by all satellites (assumption)"),
                     ("candidate_segments", "-"), ("eligible_segments", "-"), ("total_candidate_hours", "h"),
                     ("total_assigned_hours", "h (includes setup)"), ("total_useful_hours", "h (transmit time)")]:
            da.append([k, alloc.get(k), u])
        da.append(["setup_minutes", alloc["policy"].get("setup_minutes"), "min, ASSUMPTION (not a verified DSN requirement)"])
        da.append(["min_contact_minutes", alloc["policy"].get("min_contact_minutes"), "min = setup + minimum useful transmit"])
        da.append(["allocation_note", alloc.get("allocation_note"), ""])
        da.append(["geometry_note", alloc.get("geometry_note"), ""])
        _header(da)
        _widths(da, [32, 60, 50])
    checks = wb.create_sheet("Checks")
    checks.append(["Check", "Workbook (formula)", "Python engine", "Relative tolerance", "Result"])
    tel_json = _load(out / "telemetry_generation.json")
    hga_json = _load(out / "hga_sizing.json")
    link_json = _load(out / "link_budget.json")
    linked = link_json.get("status") == "PRELIMINARY"
    rows_c = [("Telemetry total per satellite (bit/s)", "=tel_total_bps", tel_json.get("total_rate_bps_per_spacecraft"), 1e-9),
              ("HGA idealized gain (dBi)", "=hga_gain_dbi", hga_json.get("calculated_idealized_gain_dbi"), 1e-9),
              ("Free-space path loss (dB)", "=Link!B2", link_json.get("free_space_path_loss_db") if linked else None, 1e-9),
              ("Minimum RF power (W)", "=Link!B5", link_json.get("minimum_tx_rf_w_with_design_margin") if linked else None, 1e-3)]
    for i, (label, f, py, tol) in enumerate(rows_c, start=2):
        checks.append([label, f, py if py is not None else "n/a (inputs missing)", tol,
                       f'=IF(AND(ISNUMBER(B{i}),ISNUMBER(C{i})),IF(ABS(B{i}/C{i}-1)<=D{i},"OK","DIFF"),"n/a (inputs missing)")'])
    if sim.get("satellites") and "Satellites" in wb.sheetnames:
        n = checks.max_row + 1
        checks.append(["Data conservation over all satellites (Mbit)", f"=SUMPRODUCT(ABS(Satellites!{bal_letter}2:{bal_letter}{sat_rows}))", 0, 1e-6,
                       f'=IF(B{n}<=D{n},"OK","DIFF")'])
    _header(checks)
    _widths(checks, [48, 22, 24, 18, 24])

    lim = wb.create_sheet("Limitations")
    for row in [["Issue", "Status"],
                ["Orbit geometry", "Historical windows shifted to 2030; NOT physical propagation"],
                ["DSN", "Hypothetical allocation; NOT booked"],
                ["Telemetry", "PDF values or explicitly PRELIMINARY assumptions"],
                ["HGA", "0.38 m assumed, not selected hardware"],
                ["Link budget", "Distance, G/T, Eb/N0, losses and margin are assumptions until verified"],
                ["Mass", "11.40 kg TT&C/OBDH allocation, not itemized verified mass"]]:
        lim.append(row)
    _header(lim)
    _widths(lim, [20, 90])

    target = Path(output) if Path(output).is_absolute() else root / output
    target.parent.mkdir(parents=True, exist_ok=True)
    wb.save(target)
    return target


if __name__ == "__main__":
    print(export())
