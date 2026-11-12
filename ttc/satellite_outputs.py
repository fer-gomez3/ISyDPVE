"""Per-satellite JSON/CSV outputs for the eight SELENA spacecraft (scenario results)."""
import csv
import json
from pathlib import Path


def write(out_dir="outputs"):
    out = Path(out_dir)
    tel = json.loads((out / "telemetry_generation.json").read_text(encoding="utf-8"))
    sim = json.loads((out / "downlink_simulation.json").read_text(encoding="utf-8"))
    alloc = json.loads((out / "dsn_allocation_summary.json").read_text(encoding="utf-8"))
    windows = []
    wpath = out / "dsn_allocated_windows.csv"
    if wpath.exists():
        with wpath.open(encoding="utf-8", newline="") as f:
            windows = list(csv.DictReader(f))
    eng = {}
    ep = out / "subsystem_engineering.json"
    if ep.exists():
        eng = {r["subsystem"]: r.get("engineering", {}) for r in json.loads(ep.read_text(encoding="utf-8"))["subsystems"]}
    folder = out / "per_satellite"
    folder.mkdir(parents=True, exist_ok=True)
    summary = []
    for sat, result in sim.get("satellites", {}).items():
        a = alloc["by_satellite"].get(sat, {})
        mine = [w for w in windows if w["satellite"] == sat and w["eligible"] == "True"]
        contacts = [c for c in sim["contacts"] if c["satellite"] == sat]
        worst = max(result["by_stream"].items(), key=lambda kv: kv[1]["max_data_age_hours"] / kv[1]["deadline_hours"])
        record = {
            "satellite": sat,
            "status": "HYPOTHETICAL_SCENARIO_NOT_VALIDATED_GEOMETRY",
            "telemetry_rates_bps": {r["subsystem"]: r["rate_bps"] for r in tel["subsystems"]},
            "telemetry_total_bps": tel["total_rate_bps_per_spacecraft"],
            "telemetry_breakdown": [{k: r[k] for k in ("subsystem", "rate_bps", "rate_basis", "itemised_bps",
                                                       "unitemised_remainder_bps", "pdf_reference_bps", "validation_status")}
                                    for r in tel["subsystems"]],
            "telemetry_itemised_bps": tel["total_itemised_bps_per_spacecraft"],
            "telemetry_unitemised_remainder_bps": tel["total_unitemised_remainder_bps_per_spacecraft"],
            "obdh_buffer": {"minimum_buffer_mbit_from_peak_backlog": result["peak_backlog_mbit"],
                            "software_memory_bytes": eng.get("obdh_hk_logs", {}).get("software_memory_bytes"),
                            "note": "Peak backlog under the shifted-2020 hypothetical contacts; software memory is a placeholder engineering input"},
            "dsn_allocation": a,
            "allocated_windows": mine,
            "downlink": {k: v for k, v in result.items() if k != "by_stream"},
            "by_stream": result["by_stream"],
            "contacts": contacts,
        }
        (folder / f"{sat}.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        summary.append({
            "satellite": sat,
            "telemetry_total_bps": tel["total_rate_bps_per_spacecraft"],
            "telemetry_itemised_bps": tel["total_itemised_bps_per_spacecraft"],
            "telemetry_unitemised_remainder_bps": tel["total_unitemised_remainder_bps_per_spacecraft"],
            "candidate_hours": a.get("candidate_hours"),
            "assigned_hours": a.get("assigned_hours"),
            "useful_tx_hours": a.get("useful_hours"),
            "contacts_used": len(contacts),
            "generated_mbit": result["generated_mbit"],
            "downloaded_mbit": result["downloaded_mbit"],
            "remaining_mbit": result["remaining_mbit"],
            "peak_backlog_mbit": result["peak_backlog_mbit"],
            "streams_at_deadline_risk": len(result["deadline_risk_streams"]),
            "worst_stream": worst[0],
            "worst_stream_max_age_h": worst[1]["max_data_age_hours"],
            "worst_stream_deadline_h": worst[1]["deadline_hours"],
        })
    with (out / "per_satellite_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary[0]))
        w.writeheader()
        w.writerows(summary)
    return summary
