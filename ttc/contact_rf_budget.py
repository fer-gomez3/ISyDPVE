"""Antenna and RF budget sized ONLY from the contacts assigned by the DSN scheduler.

Chain: assigned contact (backlog at the start of transmission, useful transmission
time) -> required gross rate -> required EIRP (link budget) -> antenna gain /
diameter and RF power -> DC consumption, dissipated heat and energy per contact.

* Inputs are the existing preliminary hypotheses of the repository (every value
  carries its source). Nothing is invented. A missing parameter is listed and can
  be supplied (``overrides`` / CLI) to run a reference scenario.
* Candidate visibility windows are never used; ``assigned_contacts.csv`` must come
  from ``ttc.dsn_scheduler`` (status ``ASSIGNED_CONTACT_NOT_DSN_BOOKING``).
* No antenna mass, no mechanical envelope, no comparison between arbitrary
  diameters. The design is driven by the most demanding assigned contact.
* Preparation, acquisition and teardown loads are not modelled (their component
  powers are unknown); energy is for the useful transmission, plus the gimbal
  placeholder over the reservation, reported separately.

Run: python -m ttc.contact_rf_budget --input-dir outputs/dsn_pipeline
"""
import argparse
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .antenna_link_budget import antenna
from .link_budget import evaluate_link

ROOT = Path(__file__).resolve().parents[1]
STATUS = "PRELIMINARY_RF_BUDGET_FROM_ASSIGNED_CONTACTS_NOT_FLIGHT_VALIDATED"
ASSIGNED = "ASSIGNED_CONTACT_NOT_DSN_BOOKING"
CAVEAT = ("Preliminary: contacts are a hypothetical allocation (not DSN bookings) on historical or "
          "calendar-shifted visibility; RF and power inputs are unverified hypotheses of the repository.")
LINK_KEYS = ("frequency_hz", "distance_km", "rx_gt_db_per_k", "required_ebn0_db", "losses_db",
             "margin_db", "pointing_error_deg", "aperture_efficiency")
ELECTRICAL_KEYS = ("pa_efficiency", "electronics_w")


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _dt(v):
    return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc)


# ---------------------------------------------------------------- parameters
def load_parameters(overrides=None, use_hga_reference=True, root=ROOT):
    """Existing preliminary hypotheses plus overrides; every value has its source."""
    overrides = {k: v for k, v in (overrides or {}).items() if v is not None}
    comms = _json(Path(root) / "data" / "communications_budget_inputs.json")
    hga = _json(Path(root) / "data" / "hga_preliminary_design.json")
    eps = _json(Path(root) / "data" / "ttc_eps_preliminary_budget.json")
    link = comms["earth_downlink"]
    src_link = "data/communications_budget_inputs.json:earth_downlink (illustrative, not flight-validated)"
    p, src = {}, {}

    def put(key, value, source):
        p[key], src[key] = value, source

    for key, name in (("frequency_hz", "frequency_hz"), ("distance_km", "distance_km"),
                      ("rx_gt_db_per_k", "rx_gt_db_per_k"), ("required_ebn0_db", "required_ebn0_db"),
                      ("losses_db", "losses_db"), ("margin_db", "margin_db"),
                      ("pointing_error_deg", "pointing_error_deg"), ("pa_efficiency", "pa_efficiency"),
                      ("electronics_w", "electronics_w")):
        put(key, link.get(name), src_link)
    put("aperture_efficiency", link.get("tx_efficiency"), src_link + " tx_efficiency")
    put("max_tx_rf_w", comms.get("max_tx_rf_w"), "data/communications_budget_inputs.json:max_tx_rf_w (not approved)")
    put("diameter_m", None, "not supplied")
    put("gimbal_power_w", hga.get("gimbal_power_w"), "data/hga_preliminary_design.json:gimbal_power_w (placeholder, Structures)")
    put("active_dc_allowance_w", eps.get("active_ttc_dc_budget_w_per_spacecraft"),
        "data/ttc_eps_preliminary_budget.json (provisional EPS/TCS allocation)")
    put("thermal_allowance_w", eps.get("thermal_upper_bound_w_per_spacecraft"),
        "data/ttc_eps_preliminary_budget.json (provisional upper bound)")
    reference = None
    if use_hga_reference and "diameter_m" not in overrides:
        put("diameter_m", hga.get("diameter_m"), "data/hga_preliminary_design.json:diameter_m (HYPOTHETICAL_NOT_SELECTED)")
        if "aperture_efficiency" not in overrides:
            put("aperture_efficiency", hga.get("aperture_efficiency"),
                "data/hga_preliminary_design.json:aperture_efficiency (HYPOTHETICAL_NOT_SELECTED)")
        reference = "data/hga_preliminary_design.json"
    for k, v in overrides.items():
        if k not in p:
            raise ValueError(f"Unknown parameter {k!r}")
        put(k, v, "user override")
    for k in ("frequency_hz", "distance_km", "aperture_efficiency", "diameter_m", "max_tx_rf_w", "pa_efficiency"):
        if p[k] is not None and float(p[k]) <= 0:
            raise ValueError(f"{k} must be positive")
    if p["aperture_efficiency"] is not None and float(p["aperture_efficiency"]) > 1:
        raise ValueError("aperture_efficiency must be in (0,1]")
    if p["pa_efficiency"] is not None and float(p["pa_efficiency"]) > 1:
        raise ValueError("pa_efficiency must be in (0,1]")
    for k in ("losses_db", "margin_db", "pointing_error_deg", "electronics_w"):
        if p[k] is not None and float(p[k]) < 0:
            raise ValueError(f"{k} must be nonnegative")
    eps_ref = {"pa_efficiency": 0.4, "electronics_w": 5.0, "tx_gain_dbi": 33.0, "rx_gt_db_per_k": 40.0,
               "source": "ttc_eps_preliminary_budget.json notes"}
    return {"values": p, "sources": src, "reference_design": reference, "eps_budget_assumptions": eps_ref,
            "eps_budget_nominal_dc_w": eps.get("nominal_minimum_link_dc_w")}


def missing_parameters(p):
    values = p["values"]
    miss = [k for k in LINK_KEYS if values.get(k) is None]
    if values.get("diameter_m") is None and values.get("max_tx_rf_w") is None:
        miss.append("diameter_m or max_tx_rf_w (design constraint: supply one to run a reference scenario)")
    return miss


# -------------------------------------------------------------------- contacts
def load_assigned_contacts(directory):
    path = Path(directory) / "assigned_contacts.csv"
    if not path.exists():
        return [], "MISSING_ASSIGNED_CONTACTS"
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if any(r.get("status") != ASSIGNED for r in rows):
        return [], "NOT_ASSIGNED_CONTACTS"
    needed = ("satellite", "station", "start_utc", "end_utc", "reserved_minutes", "tx_start_utc", "tx_end_utc",
              "useful_tx_minutes", "backlog_at_tx_start_mbit", "downloaded_mbit", "backlog_after_tx_mbit",
              "backlog_drained_at_tx_end")
    if rows and any(k not in rows[0] for k in needed):
        return [], "ASSIGNED_CONTACTS_MISSING_COLUMNS_REGENERATE_PIPELINE"
    return rows, "OK"


def contact_requirements(rows, generation_bps, overhead):
    """Rate needed to empty the queue within the assigned useful transmission time."""
    if generation_bps < 0 or not 0 <= overhead < 1:
        raise ValueError("Invalid generation rate or overhead")
    out = []
    for r in rows:
        tx_s = float(r["useful_tx_minutes"]) * 60
        if tx_s <= 0:
            continue
        backlog = float(r["backlog_at_tx_start_mbit"]) * 1e6
        net = backlog / tx_s + generation_bps
        out.append({**r, "tx_seconds": tx_s, "required_net_bps": net,
                    "required_gross_bps": net / (1 - overhead)})
    return out


# ------------------------------------------------------------------------ RF
def required_eirp_dbw(p, gross_bps):
    v = p["values"]
    b = evaluate_link(dict(distance_km=v["distance_km"], frequency_hz=v["frequency_hz"], tx_gain_dbi=0,
                           rx_gt_db_per_k=v["rx_gt_db_per_k"], data_rate_bps=gross_bps,
                           required_ebn0_db=v["required_ebn0_db"], losses_db=v["losses_db"],
                           margin_db=v["margin_db"]))
    return b["required_eirp_dbw"], b["free_space_path_loss_db"]


def effective_gain(p, diameter_m):
    v = p["values"]
    a = antenna(float(v["frequency_hz"]), diameter_m, float(v["aperture_efficiency"]), float(v["pointing_error_deg"]))
    return {**a, "effective_gain_dbi": a["gain_dbi"] + a["pointing_loss_db"]}


def minimum_diameter(p, required_gain_dbi, lo=1e-3, hi=100.0, steps=4000):
    """Smallest diameter whose gain after pointing loss reaches the requirement (None if none up to 100 m)."""
    prev = lo
    for i in range(steps + 1):
        d = lo * (hi / lo) ** (i / steps)
        if effective_gain(p, d)["effective_gain_dbi"] >= required_gain_dbi:
            left, right = prev, d
            for _ in range(80):
                mid = (left + right) / 2
                if effective_gain(p, mid)["effective_gain_dbi"] >= required_gain_dbi:
                    right = mid
                else:
                    left = mid
            return right
        prev = d
    return None


def dc_and_heat(p, rf_w):
    v = p["values"]
    if v.get("pa_efficiency") is None or v.get("electronics_w") is None:
        return None, None
    dc = rf_w / float(v["pa_efficiency"]) + float(v["electronics_w"])
    return dc, dc - rf_w


def _db(x):
    return 10 * math.log10(x)


def _day_split(start, end):
    cur = start
    while cur < end:
        nxt = min(end, datetime.combine(cur.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
        yield cur.date().isoformat(), (nxt - cur).total_seconds()
        cur = nxt


# ------------------------------------------------------------------- the budget
def budget(contacts, params, generation_bps, overhead, scheduler_gross_bps=None):
    """Design-driving contact -> antenna / RF; per-contact power, heat and energy."""
    v = params["values"]
    miss = missing_parameters(params)
    reqs = contact_requirements(contacts, generation_bps, overhead)
    result = {"status": STATUS, "caveat": CAVEAT, "missing_parameters": miss,
              "contacts_used": len(reqs), "contact_source": "assigned_contacts.csv (ttc.dsn_scheduler)",
              "parameters": {k: {"value": params["values"][k], "source": params["sources"][k]} for k in params["values"]},
              "excluded": ["antenna mass", "mechanical envelope", "lunar-surface return link",
                           "preparation/acquisition/teardown electrical loads (component powers unknown)"]}
    if not reqs:
        result.update(status="NO_ASSIGNED_CONTACTS_WITH_TRANSMISSION", design=None, contacts=[], energy_by_day=[])
        return result
    link_missing = [k for k in LINK_KEYS if v.get(k) is None]
    result["requirements"] = {
        "generation_bps": generation_bps, "overhead_fraction": overhead,
        "definition": "rate that empties the queue (backlog at start of transmission plus generation) in the assigned useful transmission time",
        "max_required_gross_bps": max(r["required_gross_bps"] for r in reqs),
        "min_required_gross_bps": min(r["required_gross_bps"] for r in reqs),
        "scheduler_gross_bps": scheduler_gross_bps}
    if link_missing:
        result.update(status="MISSING_PARAMETERS", design=None, contacts=[], energy_by_day=[])
        return result
    for r in reqs:
        r["required_eirp_dbw"], r["free_space_path_loss_db"] = required_eirp_dbw(params, r["required_gross_bps"])
    driver = max(reqs, key=lambda r: r["required_eirp_dbw"])
    eirp_req = driver["required_eirp_dbw"]
    design = {"driving_contact": {"satellite": driver["satellite"], "station": driver["station"],
                                  "start_utc": driver["start_utc"], "useful_tx_minutes": float(driver["useful_tx_minutes"]),
                                  "backlog_at_tx_start_mbit": float(driver["backlog_at_tx_start_mbit"]),
                                  "backlog_after_tx_mbit": float(driver["backlog_after_tx_mbit"]),
                                  "limited_by": ("visibility window or horizon (queue not emptied at the scheduler rate)"
                                                 if float(driver["backlog_after_tx_mbit"]) > 1e-3 else "none (queue emptied)"),
                                  "required_gross_bps": driver["required_gross_bps"]},
              "required_eirp_dbw": eirp_req, "mode": None}
    diameter = None
    cap = v.get("max_tx_rf_w")
    if v.get("diameter_m") is not None:
        diameter = float(v["diameter_m"])
        design["mode"] = "DIAMETER_GIVEN_RF_POWER_SOLVED"
    elif cap is not None:
        d = minimum_diameter(params, eirp_req - _db(float(cap)))
        if d is None:
            result.update(status="NO_FEASIBLE_APERTURE_FOR_RF_POWER_CAP", design=design, contacts=[], energy_by_day=[])
            return result
        diameter = d
        design["mode"] = "RF_POWER_CAP_GIVEN_DIAMETER_SOLVED"
    else:
        result.update(status="MISSING_PARAMETERS", design=design, contacts=[], energy_by_day=[])
        return result
    a = effective_gain(params, diameter)
    rf_w = 10 ** ((eirp_req - a["effective_gain_dbi"]) / 10)
    dc, heat = dc_and_heat(params, rf_w)
    design.update(diameter_m=diameter, gain_dbi=a["gain_dbi"], pointing_loss_db=a["pointing_loss_db"],
                  effective_gain_dbi=a["effective_gain_dbi"], beamwidth_3db_deg=a["beamwidth_3db_deg"],
                  pointing_error_over_beamwidth=float(v["pointing_error_deg"]) / a["beamwidth_3db_deg"],
                  rf_power_w=rf_w, rf_power_dbw=_db(rf_w), eirp_dbw=_db(rf_w) + a["effective_gain_dbi"],
                  tx_dc_w=dc, tx_heat_w=heat,
                  rf_cap_w=None if cap is None else float(cap),
                  within_rf_cap=None if cap is None else rf_w <= float(cap) * (1 + 1e-6))
    rows, by_day = [], {}
    gimbal = v.get("gimbal_power_w")
    for r in sorted(reqs, key=lambda r: (r["start_utc"], r["satellite"])):
        p_min = 10 ** ((r["required_eirp_dbw"] - a["effective_gain_dbi"]) / 10)
        dc_i, heat_i = dc_and_heat(params, p_min)
        t_h = r["tx_seconds"] / 3600
        row = {"satellite": r["satellite"], "station": r["station"], "start_utc": r["start_utc"], "end_utc": r["end_utc"],
               "tx_start_utc": r["tx_start_utc"], "tx_end_utc": r["tx_end_utc"],
               "reserved_minutes": float(r["reserved_minutes"]), "useful_tx_minutes": float(r["useful_tx_minutes"]),
               "backlog_at_tx_start_mbit": float(r["backlog_at_tx_start_mbit"]),
               "downloaded_mbit": float(r["downloaded_mbit"]),
               "backlog_after_tx_mbit": float(r["backlog_after_tx_mbit"]),
               "backlog_drained_at_tx_end": r["backlog_drained_at_tx_end"],
               "required_net_bps": r["required_net_bps"], "required_gross_bps": r["required_gross_bps"],
               "required_eirp_dbw": r["required_eirp_dbw"], "min_rf_power_w": p_min,
               "link_margin_db_at_design_point": (_db(rf_w) + a["effective_gain_dbi"]) - r["required_eirp_dbw"],
               "design_rf_power_w": rf_w, "design_dc_w": dc, "design_heat_w": heat,
               "energy_tx_wh": None if dc is None else dc * t_h,
               "heat_tx_wh": None if heat is None else heat * t_h,
               "energy_tx_wh_if_power_follows_rate": None if dc_i is None else dc_i * t_h,
               "gimbal_placeholder_wh_over_reservation": None if gimbal is None else float(gimbal) * float(r["reserved_minutes"]) / 60,
               "driving": r is driver}
        rows.append(row)
        if dc is not None:
            for day, secs in _day_split(_dt(r["tx_start_utc"]), _dt(r["tx_end_utc"])):
                key = (r["satellite"], day)
                acc = by_day.setdefault(key, {"satellite": r["satellite"], "date_utc": day, "tx_hours": 0.0,
                                              "energy_tx_wh": 0.0, "heat_tx_wh": 0.0})
                acc["tx_hours"] += secs / 3600
                acc["energy_tx_wh"] += dc * secs / 3600
                acc["heat_tx_wh"] += heat * secs / 3600
    if scheduler_gross_bps:
        e2, _ = required_eirp_dbw(params, float(scheduler_gross_bps))
        p2 = 10 ** ((e2 - a["effective_gain_dbi"]) / 10)
        dc2, h2 = dc_and_heat(params, p2)
        result["design_at_scheduler_rate"] = {
            "basis": "gross rate assumed by the scheduler to size the contacts", "gross_bps": float(scheduler_gross_bps),
            "diameter_m": diameter, "required_eirp_dbw": e2, "rf_power_w": p2, "tx_dc_w": dc2, "tx_heat_w": h2}
    result.update(design=design, contacts=rows,
                  energy_by_day=[{k: (round(x, 6) if isinstance(x, float) else x) for k, x in d.items()}
                                 for d in sorted(by_day.values(), key=lambda d: (d["satellite"], d["date_utc"]))])
    result["totals"] = None if dc is None else {
        "energy_tx_wh": sum(r["energy_tx_wh"] for r in rows), "heat_tx_wh": sum(r["heat_tx_wh"] for r in rows),
        "tx_hours": sum(r["useful_tx_minutes"] for r in rows) / 60,
        "energy_tx_wh_if_power_follows_rate": sum(r["energy_tx_wh_if_power_follows_rate"] for r in rows)}
    return result


# ------------------------------------------------------------------ coherence
def _alt_power(params, design, key, value):
    """RF power at the design diameter with one parameter replaced (one-at-a-time effect)."""
    alt = {"values": {**params["values"], key: value}, "sources": params["sources"]}
    eirp, _ = required_eirp_dbw(alt, design["driving_contact"]["required_gross_bps"])
    a = effective_gain(alt, design["diameter_m"])
    return 10 ** ((eirp - a["effective_gain_dbi"]) / 10)


def coherence(result, params):
    """Checks against the EPS, Thermal and ADCS/Structures data of the repository."""
    d, v = result.get("design"), params["values"]
    checks = []

    def add(cid, sub, item, value, ref, status, note):
        checks.append({"id": cid, "subsystem": sub, "item": item, "value": value, "reference": ref,
                       "status": status, "note": note})

    if not d or d.get("tx_dc_w") is None:
        add("RF-0", "TT&C", "RF budget", None, None, "PENDING",
            "design point not available: " + "; ".join(result.get("missing_parameters") or ["see status"]))
        return checks
    gimbal = float(v["gimbal_power_w"]) if v.get("gimbal_power_w") is not None else None
    allow = v.get("active_dc_allowance_w")
    if allow is not None:
        total = d["tx_dc_w"] + (gimbal or 0.0)
        ok = total <= float(allow)
        add("EPS-1", "EPS", "Active TT&C DC power (TX DC + gimbal placeholder) vs EPS allocation",
            round(total, 3), float(allow), "PASS" if ok else "FAIL",
            f"TX DC {d['tx_dc_w']:.2f} W + gimbal placeholder {0 if gimbal is None else gimbal:g} W; margin {float(allow)-total:+.2f} W. "
            "The allocation excludes pointing-actuator power per ttc_eps_preliminary_budget.json.")
    ea = params["eps_budget_assumptions"]
    diffs = []
    if v.get("pa_efficiency") is not None and abs(float(v["pa_efficiency"]) - ea["pa_efficiency"]) > 1e-9:
        diffs.append(f"PA efficiency {v['pa_efficiency']} vs {ea['pa_efficiency']}")
    if v.get("electronics_w") is not None and abs(float(v["electronics_w"]) - ea["electronics_w"]) > 1e-9:
        diffs.append(f"electronics {v['electronics_w']} W vs {ea['electronics_w']} W")
    if v.get("rx_gt_db_per_k") is not None and abs(float(v["rx_gt_db_per_k"]) - ea["rx_gt_db_per_k"]) > 1e-9:
        diffs.append(f"ground G/T {v['rx_gt_db_per_k']} vs {ea['rx_gt_db_per_k']} dB/K")
    if abs(d["effective_gain_dbi"] - ea["tx_gain_dbi"]) > 0.05:
        diffs.append(f"antenna gain {d['effective_gain_dbi']:.2f} vs {ea['tx_gain_dbi']} dBi")
    add("EPS-2", "EPS", "Assumptions behind the 15 W allocation", "; ".join(diffs) or "consistent", None,
        "WARNING" if diffs else "PASS",
        "The EPS allocation was derived with different RF assumptions; re-derive it from this budget." if diffs else "")
    th = v.get("thermal_allowance_w")
    if th is not None:
        add("TCS-1", "Thermal", "Heat dissipated during transmission vs thermal upper bound",
            round(d["tx_heat_w"], 3), float(th), "PASS" if d["tx_heat_w"] <= float(th) else "FAIL",
            "The upper bound assumes all budgeted power could dissipate as heat (provisional).")
    add("TCS-2", "Thermal", "TT&C equipment temperature limits (-10/+55 C operational)", None, None, "PENDING",
        "No thermal model of the TT&C equipment; heat per contact is provided as an input.")
    add("ADCS-1", "ADCS/Structures", "Half-power beamwidth and assumed pointing error",
        f"{d['beamwidth_3db_deg']:.2f} deg; error {float(v['pointing_error_deg']):.2f} deg ({d['pointing_error_over_beamwidth']:.3f} of beamwidth); loss {d['pointing_loss_db']:.3f} dB",
        None, "INFO", "AOCS/Structures must confirm that the gimbal and attitude control deliver this pointing error.")
    add("ADCS-2", "ADCS/Structures", "Slew, acquisition and tracking requirements", None, None, "PENDING",
        "Needs the orbit and the Earth direction history; the gimbal power (2 W) and mass belong to Structures.")
    add("EPS-3", "EPS", "OBC 25-30 W inside the 145 W avionics line with TX load", None, 145.0, "PENDING",
        "The other avionics and bus loads are not available; only OBC and TX are known.")
    add("EPS-4", "EPS", "Standby, receive, simultaneous, slew and acquisition powers", None, None, "PENDING",
        "Component powers are null in the data; energy covers transmission (and the gimbal placeholder) only.")
    add("RF-1", "TT&C", "Link margin at the design point for the driving contact", 0.0, None, "PASS",
        "Design closes the link with the configured margin by construction; other contacts have extra margin.")
    add("RF-2", "TT&C", "Lunar-surface return link", None, None, "PENDING",
        "Not in the documented C&DH scope (data/communications_budget_inputs.json).")
    sched = (result.get("requirements") or {}).get("scheduler_gross_bps")
    if sched:
        mx = result["requirements"]["max_required_gross_bps"]
        add("DSN-1", "DSN/OBDH", "Highest required gross rate vs gross rate assumed by the scheduler",
            round(mx), sched, "PASS" if mx <= sched * (1 + 1e-6) else "FAIL",
            "Contacts were sized with the scheduler rate; a higher requirement means a contact is too short for the queue." +
            ("" if mx <= sched * (1 + 1e-6) else " The antenna is sized for the higher rate."))
    cap = d.get("rf_cap_w")
    if cap is not None:
        add("RF-3", "TT&C", "RF power vs supplied cap", round(d["rf_power_w"], 4), cap,
            "PASS" if d["within_rf_cap"] else "FAIL", "")
    return checks


def parameter_conflicts(result, params):
    """Documented hypothesis sets that disagree; one-at-a-time effect on the RF power."""
    d = result.get("design")
    if not d or d.get("rf_power_w") is None:
        return []
    v = params["values"]
    base = d["rf_power_w"]
    alts = [("required_ebn0_db", 10.0, "docs/technical-report.md section 4.2 quotes Eb/N0 10 dB"),
            ("losses_db", 3.0, "docs/technical-report.md section 4.2 quotes other losses 3 dB"),
            ("rx_gt_db_per_k", 40.0, "ttc_eps_preliminary_budget.json notes assume 40 dB/K"),
            ("aperture_efficiency", 0.55 if abs(float(v["aperture_efficiency"]) - 0.6) < 1e-9 else 0.6,
             "data/communications_budget_inputs.json uses 0.55; data/hga_preliminary_design.json uses 0.6")]
    out = []
    for key, alt, why in alts:
        if v.get(key) is None or abs(float(v[key]) - alt) < 1e-12:
            continue
        p = _alt_power(params, d, key, alt)
        out.append({"parameter": key, "used": v[key], "alternative": alt, "alternative_source": why,
                    "rf_power_w_used": base, "rf_power_w_alternative": p,
                    "change_db": _db(p / base), "diameter_m_fixed": d["diameter_m"]})
    return out


# --------------------------------------------------------------------- outputs
def _csv(path, rows):
    rows = list(rows)
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["empty"])
        w.writeheader()
        w.writerows(rows)


def run(input_dir, output_dir=None, overrides=None, use_hga_reference=True, generation_bps=None,
        overhead=None, scheduler_gross_bps=None, make_figures=True):
    """Size from ``<input_dir>/assigned_contacts.csv``; write rf_budget_*.csv/json and figures."""
    src = Path(input_dir)
    out = Path(output_dir or src)
    out.mkdir(parents=True, exist_ok=True)
    params = load_parameters(overrides, use_hga_reference)
    contacts, status = load_assigned_contacts(src)
    if status != "OK":
        res = {"status": status, "caveat": CAVEAT, "design": None, "contacts": [], "energy_by_day": [],
               "missing_parameters": missing_parameters(params), "checks": [], "parameter_conflicts": []}
        (out / "rf_budget_summary.json").write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
        return res
    mq = src / "memory_queues_summary.json"
    if generation_bps is None and mq.exists():
        generation_bps = _json(mq)["generation"]["per_satellite_bps"]
    summ = src / "summary.json"
    if summ.exists():
        s = _json(summ)
        overhead = overhead if overhead is not None else s.get("overhead_fraction")
        scheduler_gross_bps = scheduler_gross_bps or s.get("scenario_downlink_gross_bps")
    if generation_bps is None or overhead is None:
        raise ValueError("generation_bps and overhead are required (no pipeline summary found)")
    res = budget(contacts, params, float(generation_bps), float(overhead), scheduler_gross_bps)
    res["checks"] = coherence(res, params)
    res["parameter_conflicts"] = parameter_conflicts(res, params)
    cons = [c["status"] for c in res["checks"]]
    res["verdict"] = {"PASS": cons.count("PASS"), "FAIL": cons.count("FAIL"), "PENDING": cons.count("PENDING"),
                      "WARNING": cons.count("WARNING")}
    (out / "rf_budget_summary.json").write_text(json.dumps(res, indent=2, default=str) + "\n", encoding="utf-8")
    if res["contacts"]:
        _csv(out / "rf_budget_by_contact.csv", [{k: (round(x, 6) if isinstance(x, float) else x) for k, x in r.items()}
                                                 for r in res["contacts"]])
        _csv(out / "rf_budget_energy_by_day.csv", res["energy_by_day"])
    _csv(out / "rf_coherence_checks.csv", res["checks"])
    if res["parameter_conflicts"]:
        _csv(out / "rf_parameter_conflicts.csv", res["parameter_conflicts"])
    if make_figures:
        res["figures"] = plot_figures(res, out / "figures")
    return res


def plot_figures(res, figures_dir):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return {"status": "MATPLOTLIB_NOT_INSTALLED", "files": []}
    rows, d = res.get("contacts") or [], res.get("design")
    if not rows or not d or rows[0].get("energy_tx_wh") is None:
        return {"status": "NO_RF_RESULTS", "files": []}
    figs = Path(figures_dir)
    figs.mkdir(parents=True, exist_ok=True)
    files = []
    labels = [f"{r['satellite'][-2:]}\n{r['start_utc'][5:10]}" for r in rows]
    x = range(len(rows))
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    ax[0].bar(x, [r["required_gross_bps"] / 1e3 for r in rows], color="tab:blue")
    sched = (res.get("requirements") or {}).get("scheduler_gross_bps")
    if sched:
        ax[0].axhline(sched / 1e3, color="k", ls="--", label=f"scheduler gross rate {sched/1e3:g} kbps")
        ax[0].legend(fontsize=7)
    ax[0].set_ylabel("Required gross rate (kbps)")
    ax[0].set_title("Rate that empties the queue in each assigned contact")
    ax[1].bar(x, [r["min_rf_power_w"] for r in rows], color="tab:orange", label="minimum for the contact")
    ax[1].axhline(d["rf_power_w"], color="r", ls="--", label=f"design RF power {d['rf_power_w']:.3f} W (driving contact)")
    ax[1].set_ylabel("RF power (W)")
    ax[1].set_title(f"RF power at D = {d['diameter_m']*100:.0f} cm, gain {d['effective_gain_dbi']:.1f} dBi")
    ax[1].legend(fontsize=7)
    for a in ax:
        a.set_xticks(list(x))
        a.set_xticklabels(labels, fontsize=6)
    fig.text(0.01, 0.005, CAVEAT, fontsize=6)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    f = figs / "rf_rate_and_power_by_contact.png"
    fig.savefig(f, dpi=130)
    plt.close(fig)
    files.append(str(f))
    fig, ax = plt.subplots(1, 2, figsize=(12, 4.2))
    w = 0.4
    ax[0].bar([i - w / 2 for i in x], [r["energy_tx_wh"] for r in rows], w, label="design power (constant)")
    ax[0].bar([i + w / 2 for i in x], [r["energy_tx_wh_if_power_follows_rate"] for r in rows], w, label="power follows rate")
    ax[0].set_ylabel("TX energy per contact (Wh)")
    ax[0].set_xticks(list(x))
    ax[0].set_xticklabels(labels, fontsize=6)
    ax[0].legend(fontsize=7)
    ax[0].set_title("Energy per contact (useful transmission only)")
    days = res.get("energy_by_day") or []
    sats = sorted({e["satellite"] for e in days})
    dates = sorted({e["date_utc"] for e in days})
    bottom = [0.0] * len(dates)
    for s in sats:
        vals = [sum(e["energy_tx_wh"] for e in days if e["satellite"] == s and e["date_utc"] == dd) for dd in dates]
        ax[1].bar(dates, vals, bottom=bottom, label=s)
        bottom = [b + v for b, v in zip(bottom, vals)]
    ax[1].set_ylabel("TX energy per UTC day (Wh)")
    ax[1].set_title("Constellation TX energy per day")
    ax[1].legend(fontsize=6, ncol=2)
    plt.setp(ax[1].get_xticklabels(), rotation=30, ha="right", fontsize=7)
    fig.text(0.01, 0.005, CAVEAT, fontsize=6)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    f = figs / "rf_energy_by_contact_and_day.png"
    fig.savefig(f, dpi=130)
    plt.close(fig)
    files.append(str(f))
    checks = {c["id"]: c for c in res.get("checks", [])}
    fig, ax = plt.subplots(figsize=(7, 4.2))
    gimbal = float(res["parameters"]["gimbal_power_w"]["value"] or 0)
    names = ["TX DC + gimbal\n(vs EPS allocation)", "TX heat\n(vs thermal bound)"]
    vals = [d["tx_dc_w"] + gimbal, d["tx_heat_w"]]
    refs = [checks.get("EPS-1", {}).get("reference"), checks.get("TCS-1", {}).get("reference")]
    ax.bar(names, vals, color=["tab:blue", "tab:red"])
    for i, r in enumerate(refs):
        if r is not None:
            ax.hlines(r, i - 0.4, i + 0.4, colors="k", linestyles="--")
            ax.text(i + 0.42, r, f"{r:g} W", va="center", fontsize=8)
    ax.set_ylabel("Power (W)")
    ax.set_title("Design point against EPS and thermal allowances")
    import textwrap
    fig.text(0.01, 0.005, "\n".join(textwrap.wrap(CAVEAT, 105)), fontsize=6)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    f = figs / "rf_power_vs_allowances.png"
    fig.savefig(f, dpi=130)
    plt.close(fig)
    files.append(str(f))
    return {"status": "OK", "files": files}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input-dir", default="outputs/dsn_pipeline",
                    help="directory with assigned_contacts.csv from dsn_pipeline / integrated_preliminary")
    ap.add_argument("--output-dir")
    ap.add_argument("--diameter-m", type=float, help="antenna diameter of the reference scenario")
    ap.add_argument("--rf-power-w", type=float, help="RF power cap: the diameter is then solved")
    for k in ("aperture-efficiency", "pa-efficiency", "electronics-w", "rx-gt-db-per-k", "required-ebn0-db",
              "losses-db", "margin-db", "pointing-error-deg", "frequency-hz", "distance-km", "gimbal-power-w",
              "active-dc-allowance-w", "thermal-allowance-w"):
        ap.add_argument("--" + k, type=float)
    ap.add_argument("--no-hga-reference", action="store_true",
                    help="do not take the diameter/efficiency of data/hga_preliminary_design.json")
    ap.add_argument("--no-figures", action="store_true")
    a = ap.parse_args(argv)
    ov = {k: getattr(a, k) for k in ("aperture_efficiency", "pa_efficiency", "electronics_w", "rx_gt_db_per_k",
                                     "required_ebn0_db", "losses_db", "margin_db", "pointing_error_deg", "frequency_hz",
                                     "distance_km", "gimbal_power_w", "active_dc_allowance_w", "thermal_allowance_w")}
    ov["diameter_m"] = a.diameter_m
    ov["max_tx_rf_w"] = a.rf_power_w
    res = run(a.input_dir, a.output_dir, ov, not a.no_hga_reference, make_figures=not a.no_figures)
    print(json.dumps({k: res.get(k) for k in ("status", "missing_parameters", "design", "totals", "verdict")}, indent=2, default=str))
    return res


if __name__ == "__main__":
    main()
