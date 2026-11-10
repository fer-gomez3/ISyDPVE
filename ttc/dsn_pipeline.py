"""Preliminary end-to-end DSN scheduling and OBDH report.

Run: python -m ttc.dsn_pipeline --downlink-bps 256000
No DSN bookings or unknown telemetry rates are fabricated.
"""
import argparse,csv,json
from datetime import timedelta
from pathlib import Path
from .contact_analysis import load_contacts,write_csv
from .dsn_allocator import verify_contacts
from .dsn_scheduler import schedule_contacts,explain_unmet_deadlines
from .engineering_calculations import calculate
from .obdh_timeline import timeline
from .contact_duration import estimate_requests
from .telemetry_generation import calculate as calculate_channels, apply_computed_rates
from .transfer_planning import stream_requirements
from .operational_interfaces import policy_seconds,usable_contacts,electrical_thermal
from .ground_delivery import simulate as simulate_deadlines, size_rate
from .memory_queues import QueueObserver, load_memory_config, write_outputs as write_queue_outputs

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CONTACTS=str(ROOT/"data"/"contacts_master.csv")

def run(contacts_path=DEFAULT_CONTACTS,output_dir="outputs/dsn_pipeline",
        downlink_bps=256000,overhead=0.2,minimum_contact_seconds=300,
        setup_seconds=0,availability=None,telemetry_profile="confirmed",pass_type=None,make_plots=True,
        daily_cap_hours=None):
    contacts=load_contacts(contacts_path)
    if not contacts:
        raise ValueError("No input windows")
    start=min(c["start"] for c in contacts);end=max(c["end"] for c in contacts)
    policy=policy_seconds(pass_type)
    prep=policy["preparation_seconds"] if setup_seconds==0 else setup_seconds
    teardown=policy["teardown_seconds"]
    sats=sorted({c["satellite"] for c in contacts})
    rates=calculate()
    known=sum(x["rate_bps"] for x in rates["telemetry"] if x["rate_bps"] is not None)
    confirmed_rate=known
    scenario_streams=None
    if telemetry_profile not in ("confirmed","scenario"):
        raise ValueError("telemetry_profile must be confirmed or scenario")
    if telemetry_profile=="scenario":
        root=Path(__file__).resolve().parents[1]
        generation=json.loads((root/"data"/"telemetry_generation_inputs.json").read_text(encoding="utf-8"))
        detail=json.loads((root/"data"/"telemetry_detailed_scenario.json").read_text(encoding="utf-8"))
        computed=calculate_channels(generation)
        apply_computed_rates(detail,computed["subsystems"])
        scenario_streams=stream_requirements(detail)
        missing=[x.get("name","unknown") for x in scenario_streams if x.get("mean_rate_bps") is None]
        if missing:
            raise ValueError("Missing scenario rates: "+", ".join(missing))
        known=sum(float(x["mean_rate_bps"]) for x in scenario_streams)
    if scenario_streams is None:
        streams=[{"name":x["subsystem"],"rate_bps":x["rate_bps"],"priority":3,"deadline_hours":24.}
                 for x in rates["telemetry"] if x["rate_bps"] is not None]
    else:
        streams=[{"name":x["name"],"rate_bps":float(x["mean_rate_bps"]),
                  "priority":int(x["priority"]),"deadline_hours":float(x["deadline_hours"])}
                 for x in scenario_streams]
    shared=json.loads((ROOT/"data"/"ttc_parameters.json").read_text(encoding="utf-8"))
    cap_hours=float(daily_cap_hours if daily_cap_hours is not None else shared["dsn_daily_network_hours"])
    # Station availability (if supplied) restricts the windows the scheduler may use.
    offered=contacts
    if availability:
        offered=[]
        for c in contacts:
            spans=availability.get(c["station"])
            if spans is None:
                offered.append(c)
            else:
                for a,b in spans:
                    lo,hi=max(c["start"],a),min(c["end"],b)
                    if hi>lo:offered.append({**c,"start":lo,"end":hi})
    unified=schedule_contacts(offered,streams,start=start,end=end,gross_bps=downlink_bps,
        overhead=overhead,prep_s=prep,teardown_s=teardown,min_tx_s=minimum_contact_seconds,
        daily_cap_s=cap_hours*3600,geometric_windows=contacts)
    schedule=unified["contacts"]
    useful=[{**c,"start":c["tx_start"],"end":c["tx_end"],"seconds":c["usable_seconds"]} for c in schedule]
    visibility=[{"satellite":c["satellite"],"station":c["station"],
                 "start_utc":c["start"].isoformat(),"end_utc":c["end"].isoformat()} for c in contacts]
    grants=[{"satellite":c["satellite"],"station":c["station"],
             "start_utc":c["start"].isoformat(),"end_utc":c["end"].isoformat()} for c in useful]
    queues=QueueObserver(streams,start,load_memory_config())
    deadline_results=simulate_deadlines(streams,visibility,grants,gross_bps=downlink_bps,
        overhead=overhead,setup_minutes=0,start_utc=start.isoformat(),end_utc=end.isoformat(),observer=queues)
    cfg=json.loads((ROOT/"data"/"communications_budget_inputs.json").read_text(encoding="utf-8"))
    powers=cfg["component_powers_w"]
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    memory_queues=write_queue_outputs(queues,deadline_results,(end-start).total_seconds()/3600,out)
    sched_rows=[{k:(v.isoformat() if hasattr(v,"isoformat") else v) for k,v in c.items()} for c in schedule]
    with (out/"candidate_schedule.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(sched_rows[0]) if sched_rows else ["satellite","station","start","end"])
        w.writeheader();w.writerows(sched_rows)
    explanation=explain_unmet_deadlines(streams,visibility,start,end,delivery=deadline_results,prep_s=prep,teardown_s=teardown,min_tx_s=minimum_contact_seconds,
        daily_cap_s=cap_hours*3600,gross_bps=downlink_bps,overhead=overhead,
        size_rate_result=size_rate(streams,visibility,grants,overhead=overhead,utilization=1,
            setup_minutes=0,step_seconds=300,max_bps=max(downlink_bps*100,10000000),tolerance_bps=100,
            start_utc=start.isoformat(),end_utc=end.isoformat()))
    result={"status":"PRELIMINARY_NOT_DSN_BOOKED","source":str(contacts_path),
        "known_generation_bps":confirmed_rate,"modeled_generation_bps":known,
        "telemetry_profile":telemetry_profile,"scenario_streams":scenario_streams,
        "scenario_warning":"ASSUMED_RATES_NOT_CONFIRMED" if scenario_streams is not None else None,
        "missing_rates":rates["missing_rates"],
        "scenario_downlink_gross_bps":downlink_bps,"overhead_fraction":overhead,
        "setup_seconds_per_contact":prep,"teardown_seconds_per_contact":teardown,
        "operational_policy":policy,"deadline_results":deadline_results,
        "allocation":unified["diagnostics"],"memory_queues":memory_queues,"deadline_explanation":explanation,
        "allocation_scope":"Historical 2020 visibility windows are NOT confirmed DSN availability for 2030; the daily DSN hours are hypothetical.",
        "contact_gaps":verify_contacts(schedule,sats,start,end),
        "satellites":{}}
    memory_timelines={}
    for sat in sats:
        assigned=[c for c in schedule if c["satellite"]==sat]
        # Setup time is excluded from transmission by shifting the beginning.
        sat_useful=[c for c in useful if c["satellite"]==sat]
        t=timeline(sat_useful,start,end,known,downlink_bps,overhead)
        from datetime import datetime
        memory_timelines[sat]=([datetime.fromisoformat(x["time_utc"]) for x in t["rows"]],
                               [x["buffer_mbit"] for x in t["rows"]])
        t["electrical_thermal"]=electrical_thermal(sat_useful,start,end,powers,rf_power_w=None)
        with (out/f"{sat}_obdh.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(t["rows"][0]))
            w.writeheader();w.writerows(t["rows"])
        result["satellites"][sat]={k:v for k,v in t.items() if k!="rows"}
    requested=estimate_requests(contacts,memory_timelines,known,downlink_bps,overhead,
        prep,teardown,minimum_contact_seconds,out/"requested_contact_durations.csv")
    result["contact_duration_output"]={
        "file":"requested_contact_durations.csv",
        "count":len(requested),
        "interpretation":"Independent per-window estimates from modeled OBDH backlog; NOT a conflict-free DSN allocation",
        "assumptions":"Uses backlog from the scheduled simulation, and accounts for telemetry generated during transmission; no simultaneous contacts",
    }
    # Traceability against report-confirmed telemetry and hardware interfaces.
    comparison=[
        {"parameter":"Payload housekeeping","report_value":100.0,
         "calculated_value":next((x["rate_bps"] for x in streams if x["name"]=="payload_housekeeping"),None),
         "unit":"bps","status":"DOCUMENTED_AGGREGATE_OR_SCENARIO","note":"PDF rate; itemised channel inventory incomplete"},
        {"parameter":"Structures housekeeping","report_value":32.0,
         "calculated_value":next((x["rate_bps"] for x in streams if x["name"]=="structures_mechanisms"),None),
         "unit":"bps","status":"DOCUMENTED_AGGREGATE_OR_SCENARIO","note":"PDF rate; itemised channel inventory incomplete"},
        {"parameter":"TT&C + OBDH mass allocation","report_value":11.4,
         "calculated_value":None,"unit":"kg","status":"MISSING_HARDWARE_MASSES",
         "note":"No component mass estimate or antenna mass fabricated"},
        {"parameter":"OBC nominal power reference minimum","report_value":25.0,
         "calculated_value":None,"unit":"W","status":"NOT_A_MEASURED_COMPONENT_DRAW",
         "note":"Reference range 25-30 W; cannot infer complete TT&C bus load"},
        {"parameter":"OBC nominal power reference maximum","report_value":30.0,
         "calculated_value":None,"unit":"W","status":"NOT_A_MEASURED_COMPONENT_DRAW",
         "note":"Avoid double-counting OBC allocation in EPS"},
    ]
    for row in comparison:
        a,b=row["report_value"],row["calculated_value"]
        row["difference"]=None if a is None or b is None else b-a
    result["report_comparison"]=comparison
    with (out/"report_comparison.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(comparison[0]))
        writer.writeheader();writer.writerows(comparison)
    if make_plots:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            result["plot_status"]="MATPLOTLIB_NOT_INSTALLED"
        else:
            from datetime import datetime
            for sat in sats:
                with (out/f"{sat}_obdh.csv").open(newline="",encoding="utf-8") as f:
                    rows=list(csv.DictReader(f))
                times=[datetime.fromisoformat(x["time_utc"]) for x in rows]
                fig,axes=plt.subplots(3,1,figsize=(11,8),sharex=True)
                axes[0].plot(times,[float(x["buffer_mbit"]) for x in rows])
                axes[0].set_ylabel("Buffer (Mbit)")
                axes[1].plot(times,[float(x["downlinked_cumulative_mbit"]) for x in rows])
                axes[1].set_ylabel("Downlinked (Mbit)")
                axes[2].step(times,[int(x["contact_active"]=="True") for x in rows],where="post")
                axes[2].set_ylabel("TX active");axes[2].set_xlabel("UTC")
                fig.suptitle(f"SELENA {sat} — preliminary allocated DSN scenario")
                fig.autofmt_xdate();fig.tight_layout()
                fig.savefig(out/f"{sat}_obdh.png",dpi=140);plt.close(fig)
            result["plot_status"]="GENERATED"
    (out/"summary.json").write_text(json.dumps(result,indent=2,default=str)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--contacts",default=DEFAULT_CONTACTS)
    p.add_argument("--output-dir",default="outputs/dsn_pipeline")
    p.add_argument("--downlink-bps",type=float,default=256000)
    p.add_argument("--overhead",type=float,default=0.2)
    p.add_argument("--minimum-contact-seconds",type=float,default=300)
    p.add_argument("--setup-seconds",type=float,default=0)
    p.add_argument("--daily-cap-hours",type=float,default=None,help="shared DSN hours per UTC day (default: data/ttc_parameters.json)")
    p.add_argument("--pass-type",choices=["standard_ttc","ranging","downlink_only","uplink_downlink"])
    p.add_argument("--telemetry-profile",choices=["confirmed","scenario"],default="confirmed")
    a=p.parse_args()
    print(json.dumps(run(a.contacts,a.output_dir,a.downlink_bps,a.overhead,
                         a.minimum_contact_seconds,a.setup_seconds,telemetry_profile=a.telemetry_profile,pass_type=a.pass_type,daily_cap_hours=a.daily_cap_hours),indent=2))
