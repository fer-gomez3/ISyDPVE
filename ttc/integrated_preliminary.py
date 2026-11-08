"""Integrated SELENA preliminary TT&C assessment.

Uses one existing adaptive-storage scenario and its scheduled contacts.
Visibility is explicitly *calendar-shifted* from 2020 (not propagated).
No DSN grants, RF closure or CCSDS compliance are asserted.
"""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from .adaptive_storage import ROOT, plan as storage_plan, shift_contacts
from .contact_analysis import load_contacts
from .ground_delivery import simulate, size_rate
from .ground_requests import propose
from .ground_protocol_planner import plan as grant_plan
from .link_budget import evaluate_link
from .rf_trade_study import run as run_rf_trade

def _rows(path):
    with Path(path).open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _write_csv(path,rows):
    if not rows:return
    with Path(path).open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def run(output_dir=None, *, gross_bps=None, rf_scenario_path=None,
        run_baseline=True,step_seconds=300,visibility_path=None,grants_path=None):
    out=Path(output_dir or ROOT/"outputs")
    out.mkdir(parents=True,exist_ok=True)
    baseline=storage_plan(output_dir=out) if run_baseline else json.loads((out/"adaptive_storage_summary.json").read_text(encoding="utf-8"))
    cfg=json.loads((ROOT/"data"/"adaptive_storage_scenario.json").read_text(encoding="utf-8"))
    shared=json.loads((ROOT/"data"/"ttc_parameters.json").read_text(encoding="utf-8"))
    epoch=datetime.fromisoformat(cfg["scenario_start_utc"].replace("Z","+00:00"))
    visible=shift_contacts(load_contacts(ROOT/"data"/"contacts_master.csv"),epoch)
    horizon_end=datetime.fromisoformat(baseline["scenario_end_utc"].replace("Z","+00:00"))
    visibility=[{"satellite":w["satellite"],"station":w["station"],
        "start_utc":max(w["start"],epoch).isoformat(),
        "end_utc":min(w["end"],horizon_end).isoformat()}
        for w in visible if w["end"]>epoch and w["start"]<horizon_end]
    if visibility_path is not None:
        visibility=_rows(visibility_path)
        for w in visibility:
            if not (epoch<=datetime.fromisoformat(w["start_utc"].replace("Z","+00:00"))<horizon_end):
                raise ValueError("External visibility must match configured mission epoch/horizon")
    grants=[{"satellite":g["satellite"],"station":g["station"],
             "start_utc":g["start_utc"],"end_utc":g["end_utc"]}
            for g in _rows(grants_path or out/"adaptive_contact_schedule.csv")]
    # Use same stream requirements as adaptive_storage, rather than a second
    # contradictory hand-maintained telemetry file.
    from .telemetry_generation import calculate, apply_computed_rates
    from .transfer_planning import stream_requirements
    tel=json.loads((ROOT/"data"/"telemetry_detailed_scenario.json").read_text(encoding="utf-8"))
    generation=json.loads((ROOT/"data"/"telemetry_generation_inputs.json").read_text(encoding="utf-8"))
    apply_computed_rates(tel,calculate(generation)["subsystems"])
    stream_reqs=stream_requirements(tel)
    streams=[]
    for s in stream_reqs:
        if s.get("mean_rate_bps") is None:continue
        streams.append({"name":s.get("name",s.get("subsystem","unknown")),
            "rate_bps":float(s["mean_rate_bps"]),
            "priority":int(s.get("priority",3)),
            "deadline_hours":float(s["deadline_hours"])})
    if len({s["name"] for s in streams})!=len(streams):raise ValueError("Duplicate subsystem names in stream requirements")
    rate=float(gross_bps if gross_bps is not None else shared["downlink_gross_bps"])
    overhead=float(shared["protocol_overhead_fraction"])
    # Adaptive-storage has already charged station setup, acquisition and
    # teardown. Do not double-subtract it from its exported grants.
    effective_grants=[g for g in grants if g["end_utc"]>g["start_utc"]]
    requests=propose(streams,visibility,gross_bps=rate,overhead=overhead,
        setup_minutes=0,utilization=1,start_utc=epoch.isoformat(),
        end_utc=horizon_end.isoformat())
    grant_results=grant_plan(streams,visibility,effective_grants,
        utilization=1,overhead=overhead,setup_minutes=0,design_margin=0.2,epoch=epoch.isoformat())
    delivery=simulate(streams,visibility,effective_grants,gross_bps=rate,
        overhead=overhead,utilization=1,setup_minutes=0,step_seconds=step_seconds,
        start_utc=epoch.isoformat(),end_utc=horizon_end.isoformat())
    sizing=size_rate(streams,visibility,effective_grants,overhead=overhead,
        utilization=1,setup_minutes=0,step_seconds=step_seconds,
        max_bps=max(rate*100,10000000),tolerance_bps=10,
        start_utc=epoch.isoformat(),end_utc=horizon_end.isoformat())
    rf_path=Path(rf_scenario_path or ROOT/"data"/"link_budget_inputs.json")
    rf_inputs=json.loads(rf_path.read_text(encoding="utf-8"))
    rf_inputs["data_rate_bps"]=sizing["required_gross_bps"] if sizing["required_gross_bps"] is not None else rate
    rf=evaluate_link(rf_inputs)
    # Explicitly illustrative RF/EPS/TCS sensitivities, not selected hardware.
    rf_trade=run_rf_trade(config_path=ROOT/"data"/"rf_trade_assumptions.json",
        rate_bps=sizing["required_gross_bps"] or rate,
        contact_hours=sum((__import__("datetime").datetime.fromisoformat(g["end_utc"].replace("Z","+00:00"))-__import__("datetime").datetime.fromisoformat(g["start_utc"].replace("Z","+00:00"))).total_seconds() for g in effective_grants)/3600/max(1,len(effective_grants)),
        output_dir=out)
    per_sat=[{"satellite":sat,"produced_mbit":round(v["produced_bits"]/1e6,3),
              "delivered_mbit":round(v["delivered_bits_assuming_perfect_link"]/1e6,3),
              "remaining_mbit":round(v["remaining_bits"]/1e6,3),
              "peak_memory_mbit":round(v["peak_backlog_bits"]/1e6,3),
              "deadline_violations":",".join(v["deadline_violations"])}
             for sat,v in sorted(delivery["satellites"].items())]
    _write_csv(out/"integrated_satellite_summary.csv",per_sat)
    _write_csv(out/"integrated_contact_requests.csv",[
        {k:v for k,v in req.items() if k!="candidate_windows"}|
        {"candidate_count":len(req["candidate_windows"])}
        for req in requests["requests"]])
    result={"status":"PRELIMINARY_SYNTHETIC_GEOMETRY_NOT_FLIGHT_VALIDATED",
            "epoch_utc":epoch.isoformat(),"scenario_end_utc":horizon_end.isoformat(),
            "assumptions":{"contact_source":"external supplied visibility (provenance unverified)" if visibility_path else "2020 calendar-shifted visibility",
                           "ground_allocations":"external supplied grants (not confirmed bookings)" if grants_path else "hypothetical adaptive scheduler",
                           "delivery":"perfect-reception fluid-bit simulation",
                           "gross_bps":rate,"overhead_fraction":overhead,
                           "setup":"already included by adaptive_storage"},
            "baseline":baseline,"requests":requests,"grants":grant_results,
            "delivery":delivery,"required_rate":sizing,"rf_budget":rf,"rf_trade":rf_trade,
            "satellite_summary":per_sat}
    (out/"integrated_preliminary.json").write_text(json.dumps(result,indent=2,default=str)+"\n",encoding="utf-8")
    report=["# SELENA — integrated preliminary TT&C / OBDH",
        "","**PRELIMINARY ONLY.** Geometry and DSN grants require independent physical and operational verification.",
        "","## Assumptions",
        f"- Epoch: {epoch.isoformat()}; horizon end: {horizon_end.isoformat()}",
        f"- Gross downlink: {rate:,.0f} bps; protocol overhead: {overhead:.0%}.",
        "- Ground-grant inputs are hypothetical adaptive-storage allocations; setup already charged upstream.",
        "- Deadline check assumes perfect reception and constant mean telemetry generation.",
        "","## Results",
        f"- Ground contact requests: {len(requests['requests'])}; proposed slots: {len(effective_grants)}.",
        f"- All modeled deadlines met at baseline rate: **{delivery['all_deadlines_met']}**.",
        f"- Minimum modeled gross rate: **{sizing['required_gross_bps']} bps** ({sizing['status']}).",
        f"- RF link status: **{rf['status']}**. Missing inputs: {', '.join(rf.get('missing_inputs',[])) or 'none'}.",
        "- RF antenna diameter/power/energy sensitivities: rf_trade_study.csv (illustrative inputs, not hardware selection).",
        "","| Satellite | Produced (Mbit) | Delivered (Mbit) | Remaining (Mbit) | Peak backlog (Mbit) | Deadline violations |",
        "|---|---:|---:|---:|---:|---|"]
    report += [f"| {x['satellite']} | {x['produced_mbit']} | {x['delivered_mbit']} | {x['remaining_mbit']} | {x['peak_memory_mbit']} | {x['deadline_violations'] or 'None'} |" for x in per_sat]
    report += ["","## Design limitations",
        "- Neither ground availability nor geometric visibility is operationally validated.",
        "- Fluid-bit delivery is not packet-level CFDP/ACK, nor does it model bit errors.",
        "- RF closure requires measured/selected G/T, modulation/coding Eb/N0, pointing and losses.",
        "- No flight hardware qualification or guaranteed hard-deadline compliance.",
        "","See integrated_preliminary.json and CSV tables for reproducible calculations."]
    (out/"SELENA_integrated_preliminary_report.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    return {"report":str(out/"SELENA_integrated_preliminary_report.md"),
            "json":str(out/"integrated_preliminary.json"),"status":result["status"],
            "all_deadlines_met":delivery["all_deadlines_met"]}

if __name__=="__main__":
    print(json.dumps(run(),indent=2))
