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
from .ground_protocol_planner import plan as grant_plan, utc as _utc
from .dsn_scheduler import schedule_contacts, explain_unmet_deadlines
from .link_budget import evaluate_link
from .rf_trade_study import run as run_rf_trade
from .contact_rf_budget import run as rf_contact_run
from .memory_queues import QueueObserver, load_memory_config, write_outputs as write_queue_outputs

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
    grants=None if grants_path is None else [
        {"satellite":g["satellite"],"station":g["station"],
         "start_utc":g["start_utc"],"end_utc":g["end_utc"]} for g in _rows(grants_path)]
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
    # The exported grants are FULL contact reservations, not TX-only slots.
    # Setup, acquisition and teardown are deducted exactly once.
    from datetime import timedelta
    policy=json.loads((ROOT/"data"/"dsn_operational_policy.json").read_text(encoding="utf-8"))
    pass_type=cfg.get("dsn_pass_type",policy["default_pass_type"])
    setup_key={"standard_ttc":"standard_ttc_setup_minutes",
               "ranging":"ranging_setup_minutes",
               "downlink_only":"downlink_setup_minutes",
               "uplink_downlink":"uplink_downlink_setup_minutes"}[pass_type]
    preparation_minutes=float(policy[setup_key])+float(policy["acquisition_minutes"])
    teardown_minutes=float(policy["teardown_minutes"])
    total_overhead_minutes=preparation_minutes+teardown_minutes
    # Same scheduling criterion as dsn_pipeline (ttc.dsn_scheduler): geometric
    # visibility, station/satellite conflicts, pass overhead, shared daily budget,
    # critical deadlines first and then equitable sharing.
    allocation=None
    if grants is None:
        unified=schedule_contacts(
            [{"satellite":w["satellite"],"station":w["station"],
              "start":_utc(w["start_utc"]),"end":_utc(w["end_utc"])} for w in visibility],
            streams,start=epoch,end=horizon_end,gross_bps=rate,overhead=overhead,
            prep_s=preparation_minutes*60,teardown_s=teardown_minutes*60,
            min_tx_s=float(shared["min_useful_tx_minutes"])*60,
            daily_cap_s=float(shared["dsn_daily_network_hours"])*3600,step_s=300)
        allocation=unified["diagnostics"]
        grants=[{"satellite":c["satellite"],"station":c["station"],
                 "start_utc":c["start"].isoformat(),"end_utc":c["end"].isoformat()}
                for c in unified["contacts"]]
        _write_csv(out/"unified_contact_schedule.csv",[
            {k:(v.isoformat() if hasattr(v,"isoformat") else v) for k,v in c.items()}
            for c in unified["contacts"]])
    effective_grants=[g for g in grants if g["end_utc"]>g["start_utc"]]
    usable_grants=[]
    for g in effective_grants:
        start=datetime.fromisoformat(g["start_utc"].replace("Z","+00:00"))
        finish=datetime.fromisoformat(g["end_utc"].replace("Z","+00:00"))
        tx_start=start+timedelta(minutes=preparation_minutes)
        tx_end=finish-timedelta(minutes=teardown_minutes)
        if tx_end>tx_start:
            usable_grants.append({**g,"start_utc":tx_start.isoformat(),
                "end_utc":tx_end.isoformat()})
    requests=propose(streams,visibility,gross_bps=rate,overhead=overhead,
        setup_minutes=total_overhead_minutes,utilization=1,start_utc=epoch.isoformat(),
        end_utc=horizon_end.isoformat())
    grant_results=grant_plan(streams,visibility,effective_grants,
        utilization=1,overhead=overhead,setup_minutes=total_overhead_minutes,
        design_margin=0.2,epoch=epoch.isoformat())
    assigned=[]
    for g in effective_grants:
        a,b=_utc(g["start_utc"]),_utc(g["end_utc"])
        tx_a,tx_b=a+timedelta(minutes=preparation_minutes),b-timedelta(minutes=teardown_minutes)
        if tx_b<=tx_a:tx_a=tx_b=a
        assigned.append({"satellite":g["satellite"],"station":g["station"],"start":a,"end":b,
                         "tx_start":tx_a,"tx_end":tx_b})
    queues=QueueObserver(streams,epoch,load_memory_config(),contacts=assigned,visibility=visibility,
        min_tx_s=float(shared["min_useful_tx_minutes"])*60,
        satellites=sorted({w["satellite"] for w in visibility}))
    delivery=simulate(streams,visibility,usable_grants,gross_bps=rate,
        overhead=overhead,utilization=1,setup_minutes=0,step_seconds=step_seconds,
        start_utc=epoch.isoformat(),end_utc=horizon_end.isoformat(),observer=queues)
    memory_queues=write_queue_outputs(queues,delivery,(horizon_end-epoch).total_seconds()/3600,out)
    rf_contact=rf_contact_run(out,generation_bps=memory_queues["generation"]["per_satellite_bps"],
        overhead=overhead,scheduler_gross_bps=rate,make_figures=True)
    sizing=size_rate(streams,visibility,usable_grants,overhead=overhead,
        utilization=1,setup_minutes=0,step_seconds=step_seconds,
        max_bps=max(rate*100,10000000),tolerance_bps=10,
        start_utc=epoch.isoformat(),end_utc=horizon_end.isoformat())
    explanation=explain_unmet_deadlines(streams,
        [{"satellite":w["satellite"],"station":w["station"],"start":w["start_utc"],"end":w["end_utc"]} for w in visibility],
        epoch,horizon_end,delivery=delivery,prep_s=preparation_minutes*60,
        teardown_s=teardown_minutes*60,min_tx_s=float(shared["min_useful_tx_minutes"])*60,
        daily_cap_s=float(shared["dsn_daily_network_hours"])*3600,gross_bps=rate,overhead=overhead,
        size_rate_result=sizing)
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
    station_totals={}
    for g in effective_grants:
        key=g["station"]
        duration=(datetime.fromisoformat(g["end_utc"].replace("Z","+00:00"))-
                  datetime.fromisoformat(g["start_utc"].replace("Z","+00:00"))).total_seconds()
        station_totals.setdefault(key,{"station":key,"contacts":0,"granted_hours":0.0})
        station_totals[key]["contacts"]+=1
        station_totals[key]["granted_hours"]+=duration/3600
    station_summary=[{"station":x["station"],"contacts":x["contacts"],
        "granted_hours":round(x["granted_hours"],3)} for x in sorted(station_totals.values(),key=lambda v:v["station"])]
    _write_csv(out/"integrated_station_summary.csv",station_summary)
    _write_csv(out/"integrated_satellite_summary.csv",per_sat)
    _write_csv(out/"integrated_contact_requests.csv",[
        {k:v for k,v in req.items() if k!="candidate_windows"}|
        {"candidate_count":len(req["candidate_windows"])}
        for req in requests["requests"]])
    result={"status":"PRELIMINARY_EXTERNAL_GEOMETRY_UNVERIFIED" if visibility_path else "PRELIMINARY_SYNTHETIC_GEOMETRY_NOT_FLIGHT_VALIDATED",
            "epoch_utc":epoch.isoformat(),"scenario_end_utc":horizon_end.isoformat(),
            "assumptions":{"contact_source":"external supplied visibility (provenance unverified)" if visibility_path else "2020 calendar-shifted visibility",
                           "ground_allocations":"external supplied grants (not confirmed bookings)" if grants_path else "unified fair scheduler (ttc.dsn_scheduler), hypothetical, not DSN bookings",
                           "delivery":"perfect-reception fluid-bit simulation",
                           "gross_bps":rate,"overhead_fraction":overhead,
                           "setup":"full contact grants converted once to useful TX intervals","preparation_minutes":preparation_minutes,"teardown_minutes":teardown_minutes},
            "baseline":baseline,"allocation":allocation,"deadline_explanation":explanation,"memory_queues":memory_queues,"requirements":memory_queues["requirements"],"rf_contact_budget":{k:rf_contact.get(k) for k in ("status","missing_parameters","design","design_at_scheduler_rate","totals","verdict","checks","parameter_conflicts")},"requests":requests,"grants":grant_results,
            "delivery":delivery,"required_rate":sizing,"rf_budget":rf,"rf_trade":rf_trade,
            "satellite_summary":per_sat,"station_summary":station_summary}
    (out/"integrated_preliminary.json").write_text(json.dumps(result,indent=2,default=str)+"\n",encoding="utf-8")
    report=["# SELENA — integrated preliminary TT&C / OBDH",
        "","**PRELIMINARY ONLY.** Geometry and DSN grants require independent physical and operational verification.",
        "","## Assumptions",
        f"- Epoch: {epoch.isoformat()}; horizon end: {horizon_end.isoformat()}",
        f"- Gross downlink: {rate:,.0f} bps; protocol overhead: {overhead:.0%}.",
        f"- Ground-grant inputs are unverified; preparation {preparation_minutes:g} min and teardown {teardown_minutes:g} min excluded from TX.",
        "- Deadline check assumes perfect reception and constant mean telemetry generation.",
        "- Contact allocation: unified scheduler (`ttc.dsn_scheduler`); visibility is NOT confirmed DSN availability and the daily DSN budget is hypothetical." if allocation else "- Contact allocation: externally supplied grants.",
        "","## Results",
        f"- Ground contact requests: {len(requests['requests'])}; proposed slots: {len(effective_grants)}.",
        f"- All modeled deadlines met at baseline rate: **{delivery['all_deadlines_met']}**.",
        f"- Minimum modeled gross rate: **{sizing['required_gross_bps']} bps** ({sizing['status']}).",
        f"- RF link status: **{rf['status']}**. Missing inputs: {', '.join(rf.get('missing_inputs',[])) or 'none'}.",
        "- RF sizing from the ASSIGNED contacts: rf_budget_summary.json / rf_budget_by_contact.csv (section below). `rf_trade_study.csv` is a legacy illustrative sensitivity grid, not a hardware selection or a sizing.",
        "","| Satellite | Produced (Mbit) | Delivered (Mbit) | Remaining (Mbit) | Peak backlog (Mbit) | Deadline violations |",
        "|---|---:|---:|---:|---:|---|"]
    report += [f"| {x['satellite']} | {x['produced_mbit']} | {x['delivered_mbit']} | {x['remaining_mbit']} | {x['peak_memory_mbit']} | {x['deadline_violations'] or 'None'} |" for x in per_sat]
    if allocation:
        cov=allocation["coverage"]
        report += ["","## Contact allocation",
            f"- Every satellite served at least once: **{cov['all_satellites_covered']}** "
            f"(coverage search: {cov['initial_feasibility']}).",
            f"- Shared DSN budget used: {allocation['budget_used_hours_total']} h "
            f"(cap {allocation['policy']['daily_cap_hours']:g} h per UTC day).",
            f"- Fairness (Jain index of usable time): {allocation['jain_fairness_usable_time']}."]
        for f in cov.get("analysis",{}).get("binding_constraints",[]):
            report.append(f"- Coverage constraint **{f['constraint']}**: {f['detail']}")
    mem=memory_queues["memory"];gen=memory_queues["generation"]
    report += ["","## OBDH memory: shared pool with logical queues per subsystem",
        f"- {len(per_sat)} independent memories of {mem['capacity_mbit']:g} Mbit ({mem['usable_mbit']:g} usable, {mem['reserve_mbit']:g} reserve); "
        "no physical partitions or quotas per subsystem; queues are logical (priority, age, maximum delivery age).",
        f"- Generated (not downloaded): {gen['per_satellite_bps']:,} bps and {gen['per_satellite_mbit_per_day']:,} Mbit/day per satellite; "
        f"{gen['constellation_bps']:,} bps, {gen['constellation_mbit_per_day']:,} Mbit/day and {gen['constellation_mbit_horizon']:,} Mbit over the horizon for {gen['constellation_satellites']} satellites.",
        f"- Downlink order: {memory_queues['download_order_policy']}.",
        "- Capacity, reserve and 65/70/85/95 % levels are simulation values, not approved requirements.",
        "","| Satellite | Peak (Mbit) | % usable | Subsystem occupying most at peak | Usable limit exceeded |","|---|---:|---:|---|---|"]
    for sat,v in memory_queues["satellites"].items():
        top=max(v["by_stream"].items(),key=lambda kv:kv[1]["queue_mbit_at_total_peak"])
        report.append(f"| {sat} | {v['peak_total_mbit']} | {v['peak_fraction_of_usable']:.1%} | {top[0]} ({top[1]['queue_mbit_at_total_peak']} Mbit) | {v['usable_limit_exceeded']} |")
    d=rf_contact.get("design")
    report += ["","## Antenna and RF budget from assigned contacts"]
    if d and d.get("tx_dc_w") is not None:
        dc=d["driving_contact"];tot=rf_contact["totals"];vd=rf_contact["verdict"]
        report += [f"- Driving contact: {dc['satellite']} at {dc['start_utc']}, {dc['useful_tx_minutes']:.1f} min useful TX, "
            f"{dc['backlog_at_tx_start_mbit']:.1f} Mbit queued, required gross rate {dc['required_gross_bps']/1e3:,.1f} kbps (limited by: {dc['limited_by']}).",
            f"- Antenna ({d['mode']}): diameter {d['diameter_m']*100:.1f} cm, gain {d['gain_dbi']:.2f} dBi, half-power beamwidth {d['beamwidth_3db_deg']:.2f} deg; "
            f"RF {d['rf_power_w']:.3f} W, DC {d['tx_dc_w']:.2f} W, heat {d['tx_heat_w']:.2f} W.",
            f"- Energy of useful transmission: {tot['energy_tx_wh']:.1f} Wh over {rf_contact['contacts_used']} contacts ({tot['tx_hours']:.2f} h); heat {tot['heat_tx_wh']:.1f} Wh.",
            f"- Coherence checks: {vd['PASS']} pass, {vd['FAIL']} fail, {vd['WARNING']} warning, {vd['PENDING']} pending (rf_coherence_checks.csv)."]
    else:
        report += [f"- Status **{rf_contact['status']}**; missing: {', '.join(rf_contact.get('missing_parameters') or []) or 'see summary'}."]
    report += ["- Excluded: antenna mass, lunar-surface return link and the electrical loads of preparation/acquisition/teardown (component powers unknown)."]
    if not explanation["all_deadlines_met"]:
        report += ["","## Why deadlines are not met"]
        report += [f"- **{f['constraint']}**: {f['detail']}" for f in explanation["findings"]]
    report += ["","## Station allocations (hypothetical)",
        "| Station | Contacts | Granted hours |","|---|---:|---:|"]
    report += [f"| {x['station']} | {x['contacts']} | {x['granted_hours']} |" for x in station_summary]
    report += ["","## RF antenna / EPS / thermal sensitivity (illustrative)",
        "| Diameter (m) | Gain (dBi) | RF power (W) | DC power (W) | Heat (W) | Contact energy (Wh) |",
        "|---|---:|---:|---:|---:|---:|"]
    report += [f"| {x['diameter_m']:.2f} | {x['gain_dbi']:.1f} | {x['required_rf_w']:.2f} | {x['tx_dc_w']:.2f} | {x['tx_heat_w']:.2f} | {x['contact_energy_wh']:.2f} |"
               for x in rf_trade["cases"]]
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
