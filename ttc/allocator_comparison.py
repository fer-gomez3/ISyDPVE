"""Before/after comparison of the DSN contact allocation criteria.

Run: python -m ttc.allocator_comparison [--output-dir outputs/allocator_comparison]

"before" = the criteria used until now
    * pipeline case: whole geometric windows chosen by earliest end
      (``dsn_allocator.allocate``), no shared daily budget;
    * integrated case: the rolling ``adaptive_storage`` schedule.
"after"  = ``dsn_scheduler.schedule_contacts`` (shared by both pipelines).

Both are evaluated with the same fluid-bit simulation (``ground_delivery``), the
same seven-stream scenario telemetry (assumed rates) and the same link
assumptions, so the differences come only from the allocation. Historical 2020
windows (and their calendar-shifted 2030 copy) are NOT confirmed DSN availability.
"""
import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .adaptive_storage import plan as storage_plan, shift_contacts
from .contact_analysis import load_contacts
from .dsn_allocator import allocate
from .dsn_scheduler import schedule_contacts
from .ground_delivery import simulate
from .operational_interfaces import policy_seconds, usable_contacts
from .telemetry_generation import calculate, apply_computed_rates
from .transfer_planning import stream_requirements

ROOT = Path(__file__).resolve().parents[1]


def scenario_streams():
    tel = json.loads((ROOT / "data" / "telemetry_detailed_scenario.json").read_text(encoding="utf-8"))
    gen = json.loads((ROOT / "data" / "telemetry_generation_inputs.json").read_text(encoding="utf-8"))
    apply_computed_rates(tel, calculate(gen)["subsystems"])
    return [{"name": s.get("name", s.get("subsystem")), "rate_bps": float(s["mean_rate_bps"]),
             "priority": int(s["priority"]), "deadline_hours": float(s["deadline_hours"])}
            for s in stream_requirements(tel) if s.get("mean_rate_bps") is not None]


def _iso(d):
    return d.isoformat()


def _evaluate(label, case, streams, visibility, reservations, start, end, gross_bps, overhead, prep, teardown):
    """reservations: dicts satellite, station, start, end (datetimes, full reservation)."""
    usable = usable_contacts(reservations, prep, teardown)
    grants = [{"satellite": c["satellite"], "station": c["station"],
               "start_utc": _iso(c["start"]), "end_utc": _iso(c["end"])} for c in usable]
    sim = simulate(streams, visibility, grants, gross_bps=gross_bps, overhead=overhead, setup_minutes=0,
                   step_seconds=300, start_utc=_iso(start), end_utc=_iso(end))
    sats = sorted({v["satellite"] for v in visibility})
    rows = []
    for sat in sats:
        mine = [r for r in reservations if r["satellite"] == sat]
        u = [c for c in usable if c["satellite"] == sat]
        s = sim["satellites"][sat]
        rows.append({"case": case, "method": label, "satellite": sat, "contacts": len(mine),
                     "reserved_hours": round(sum((r["end"] - r["start"]).total_seconds() for r in mine) / 3600, 3),
                     "usable_tx_hours": round(sum(c["seconds"] for c in u) / 3600, 3),
                     "produced_mbit": round(s["produced_bits"] / 1e6, 3),
                     "delivered_mbit": round(s["delivered_bits_assuming_perfect_link"] / 1e6, 3),
                     "peak_memory_mbit": round(s["peak_backlog_bits"] / 1e6, 3),
                     "streams_over_deadline": len(s["deadline_violations"])})
    reserved_total = sum((r["end"] - r["start"]).total_seconds() for r in reservations) / 3600
    summary = {"case": case, "method": label,
               "satellites_without_contact": [r["satellite"] for r in rows if r["contacts"] == 0],
               "contacts_total": sum(r["contacts"] for r in rows),
               "reserved_hours_total": round(reserved_total, 3),
               "delivered_mbit_total": round(sum(r["delivered_mbit"] for r in rows), 3),
               "max_peak_memory_mbit": max(r["peak_memory_mbit"] for r in rows),
               "satellites_with_deadline_violation": sum(1 for r in rows if r["streams_over_deadline"]),
               "streams_over_deadline_total": sum(r["streams_over_deadline"] for r in rows),
               "all_deadlines_met": sim["all_deadlines_met"]}
    return rows, summary


def run(output_dir="outputs/allocator_comparison", downlink_bps=256000):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    shared = json.loads((ROOT / "data" / "ttc_parameters.json").read_text(encoding="utf-8"))
    overhead = float(shared["protocol_overhead_fraction"])
    min_tx = float(shared["min_useful_tx_minutes"]) * 60
    cap_s = float(shared["dsn_daily_network_hours"]) * 3600
    pol = policy_seconds(None)
    prep, teardown = pol["preparation_seconds"], pol["teardown_seconds"]
    streams = scenario_streams()
    rows, summaries = [], []

    def new_schedule(windows, start, end):
        res = schedule_contacts(windows, streams, start=start, end=end, gross_bps=downlink_bps,
                                overhead=overhead, prep_s=prep, teardown_s=teardown, min_tx_s=min_tx,
                                daily_cap_s=cap_s)
        return res["contacts"], res["diagnostics"]

    # ---- case 1: 2020 propagator windows (pipeline horizon) -------------
    contacts = load_contacts(ROOT / "data" / "contacts_master.csv")
    start = min(c["start"] for c in contacts)
    end = max(c["end"] for c in contacts)
    vis = [{"satellite": c["satellite"], "station": c["station"], "start_utc": _iso(c["start"]),
            "end_utc": _iso(c["end"])} for c in contacts]
    old = allocate(contacts, None, max(min_tx, prep + teardown + 1), 0)
    r, s = _evaluate("before_earliest_end_whole_windows", "pipeline_2020_horizon", streams, vis, old,
                     start, end, downlink_bps, overhead, prep, teardown)
    rows += r
    summaries.append(s)
    new, diag = new_schedule(contacts, start, end)
    r, s = _evaluate("after_unified_scheduler", "pipeline_2020_horizon", streams, vis, new,
                     start, end, downlink_bps, overhead, prep, teardown)
    s["coverage"] = diag["coverage"]["initial_feasibility"]
    rows += r
    summaries.append(s)

    # ---- case 2: calendar-shifted 2030 scenario (integrated horizon) ----
    cfg = json.loads((ROOT / "data" / "adaptive_storage_scenario.json").read_text(encoding="utf-8"))
    epoch = datetime.fromisoformat(cfg["scenario_start_utc"].replace("Z", "+00:00"))
    horizon_end = epoch + timedelta(hours=float(cfg["horizon_hours"]))
    shifted = [w for w in shift_contacts(load_contacts(ROOT / "data" / "contacts_master.csv"), epoch)
               if w["end"] > epoch and w["start"] < horizon_end]
    shifted = [{**w, "start": max(w["start"], epoch), "end": min(w["end"], horizon_end)} for w in shifted]
    vis2 = [{"satellite": w["satellite"], "station": w["station"], "start_utc": _iso(w["start"]),
             "end_utc": _iso(w["end"])} for w in shifted]
    adaptive_dir = out / "adaptive_baseline"
    storage_plan(output_dir=adaptive_dir)
    with (adaptive_dir / "adaptive_contact_schedule.csv").open(newline="", encoding="utf-8") as f:
        legacy = [{"satellite": g["satellite"], "station": g["station"],
                   "start": datetime.fromisoformat(g["start_utc"].replace("Z", "+00:00")),
                   "end": datetime.fromisoformat(g["end_utc"].replace("Z", "+00:00"))} for g in csv.DictReader(f)]
    r, s = _evaluate("before_adaptive_storage_rolling", "integrated_2030_shifted_96h", streams, vis2, legacy,
                     epoch, horizon_end, downlink_bps, overhead, prep, teardown)
    rows += r
    summaries.append(s)
    new2, diag2 = new_schedule(shifted, epoch, horizon_end)
    r, s = _evaluate("after_unified_scheduler", "integrated_2030_shifted_96h", streams, vis2, new2,
                     epoch, horizon_end, downlink_bps, overhead, prep, teardown)
    s["coverage"] = diag2["coverage"]["initial_feasibility"]
    rows += r
    summaries.append(s)

    with (out / "allocator_comparison.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    result = {"status": "PRELIMINARY_NOT_DSN_BOOKED",
              "scenario_downlink_gross_bps": downlink_bps,
              "telemetry": "seven-stream scenario (assumed, unconfirmed rates)",
              "daily_budget_hours": cap_s / 3600,
              "pass_overhead_minutes": {"preparation": prep / 60, "teardown": teardown / 60},
              "visibility_note": "2020 windows (and their calendar-shifted 2030 copy) are NOT confirmed DSN availability",
              "summaries": summaries}
    (out / "allocator_comparison.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    lines = ["# DSN allocator: before vs after", "",
             "Same simulation, telemetry and link assumptions for both methods. 2020 windows are not confirmed DSN availability.", "",
             "| Case | Method | Contacts | Sats without contact | Reserved h | Delivered Mbit | Max peak memory Mbit | Sats with deadline violation |",
             "|---|---|---:|---|---:|---:|---:|---:|"]
    for s in summaries:
        lines.append(f"| {s['case']} | {s['method']} | {s['contacts_total']} | "
                     f"{', '.join(s['satellites_without_contact']) or 'none'} | {s['reserved_hours_total']} | "
                     f"{s['delivered_mbit_total']} | {s['max_peak_memory_mbit']} | "
                     f"{s['satellites_with_deadline_violation']} of 8 |")
    (out / "allocator_comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", default="outputs/allocator_comparison")
    p.add_argument("--downlink-bps", type=float, default=256000)
    a = p.parse_args()
    print(json.dumps(run(a.output_dir, a.downlink_bps), indent=2, default=str))
