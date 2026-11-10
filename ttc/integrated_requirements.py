"""Integrated TT&C requirements outputs, without invented hardware values.

Uses actual per-spacecraft telemetry rates and scheduled OBDH outputs when present.
No fixed antenna diameter, no overlapping link assumption, no data reduction.
"""
import csv
import json
from pathlib import Path
from .requirement_antenna_sizing import size

def build(output_dir, config_path="data/communications_budget_inputs.json",
          telemetry_path=None, rf_power_w=None):
    out=Path(output_dir)
    cfg=json.loads(Path(config_path).read_text(encoding="utf-8"))
    summary=json.loads((out/"overview.json").read_text(encoding="utf-8")) if (out/"overview.json").exists() else {}
    generation=json.loads((out/"telemetry_generation.json").read_text(encoding="utf-8"))
    rate=generation.get("total_rate_bps_per_spacecraft")
    if rate is None:
        return {"status":"MISSING_TELEMETRY", "missing":["total_rate_bps_per_spacecraft"]}
    rows=[]
    # Prefer actual planned contact durations if the detailed pipeline has been run.
    durations=out/"requested_contact_durations.csv"
    if durations.exists():
        with durations.open(newline="",encoding="utf-8") as f:
            candidates=list(csv.DictReader(f))
        for c in candidates:
            backlog=float(c["backlog_at_start_mbit"])
            tx=c.get("required_useful_tx_minutes")
            if not tx:
                continue
            result=size(cfg,backlog,float(tx),float(rate),rf_power_w)
            rows.append({"satellite":c["satellite"],"station":c["station"],
                         "visibility_start_utc":c["visibility_start_utc"],
                         "visibility_minutes":c["visibility_minutes"],
                         "requested_reservation_minutes":c["requested_reservation_minutes"],
                         **result})
        source="scheduled_memory_backlog_from_dsn_pipeline"
    else:
        source="NO_SCHEDULED_BACKLOG_AVAILABLE"
    if not rows:
        # Do not silently substitute one-day telemetry for actual backlog.
        status="MISSING_CONTACT_DURATIONS"
        rows=[]
    else:
        status="PRELIMINARY" if all(r["status"]=="PRELIMINARY_SIZED" for r in rows) else "INCOMPLETE_INPUTS"
    fields=list(dict.fromkeys(k for r in rows for k in r))
    if rows:
        with (out/"integrated_antenna_eps_thermal.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    missing=[]
    if rf_power_w is None and cfg.get("max_tx_rf_w") is None:
        missing.append("max_tx_rf_w")
    for name,value in cfg.get("component_powers_w",{}).items():
        if value is None: missing.append("component_powers_w."+name)
    result={"status":status,"source":source,"satellite_generation_bps":rate,
            "cases":len(rows),"missing_inputs":missing,
            "antenna_sizing_file":"integrated_antenna_eps_thermal.csv" if rows else None,
            "eps_thermal_note":"TX DC and heat only. Complete EPS/TCS budgets cannot be closed with missing subsystem component powers and thermal boundary conditions.",
            "dsn_note":"Estimates per candidate window, not an overlap-free booked allocation.",
            "geometry_note":"Historical visibility shifted to 2030 is not mission propagation."}
    (out/"integrated_antenna_eps_thermal.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result
