"""Reproducible DSN daily-hours sensitivity for SELENA PDR.

Usage: python -m ttc.dsn_sensitivity --hours 1 3 6 12 24
This is a planning scenario with calendar-shifted 2020 visibility, NOT DSN
availability or a flight-validated link.
"""
import argparse
import csv
import json
from datetime import datetime,timedelta
from pathlib import Path
from .adaptive_storage import shift_contacts
from .contact_analysis import load_contacts
from .dsn_scheduler import schedule_contacts
from .allocator_comparison import scenario_streams
from .ground_delivery import simulate
from .operational_interfaces import policy_seconds,usable_contacts

ROOT=Path(__file__).resolve().parents[1]

def run(hours=(1,3,6,12,24),output_dir="outputs/dsn_sensitivity",gross_bps=None):
    cfg=json.loads((ROOT/"data"/"adaptive_storage_scenario.json").read_text(encoding="utf-8"))
    shared=json.loads((ROOT/"data"/"ttc_parameters.json").read_text(encoding="utf-8"))
    epoch=datetime.fromisoformat(cfg["scenario_start_utc"].replace("Z","+00:00"))
    end=epoch+timedelta(hours=float(cfg["horizon_hours"]))
    windows=[{**w,"start":max(epoch,w["start"]),"end":min(end,w["end"])}
             for w in shift_contacts(load_contacts(ROOT/"data"/"contacts_master.csv"),epoch)
             if w["end"]>epoch and w["start"]<end]
    streams=scenario_streams()
    pol=policy_seconds(cfg.get("dsn_pass_type"))
    rate=float(gross_bps if gross_bps is not None else shared["downlink_gross_bps"])
    overhead=float(shared["protocol_overhead_fraction"])
    visibility=[{"satellite":w["satellite"],"station":w["station"],
                 "start_utc":w["start"].isoformat(),"end_utc":w["end"].isoformat()} for w in windows]
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    rows=[];details={}
    for h in hours:
        h=float(h)
        if not 0<h<=24:raise ValueError("Daily hours must be in (0,24]")
        alloc=schedule_contacts(windows,streams,start=epoch,end=end,gross_bps=rate,
            overhead=overhead,prep_s=pol["preparation_seconds"],
            teardown_s=pol["teardown_seconds"],
            min_tx_s=float(shared["min_useful_tx_minutes"])*60,daily_cap_s=h*3600)
        contacts=alloc["contacts"]
        tx=usable_contacts(contacts,pol["preparation_seconds"],pol["teardown_seconds"])
        grants=[{"satellite":c["satellite"],"station":c["station"],
                 "start_utc":c["start"].isoformat(),"end_utc":c["end"].isoformat()} for c in tx]
        delivery=simulate(streams,visibility,grants,gross_bps=rate,overhead=overhead,
            setup_minutes=0,step_seconds=300,start_utc=epoch.isoformat(),end_utc=end.isoformat())
        sats=delivery["satellites"]
        violations=sum(bool(v["deadline_violations"]) for v in sats.values())
        row={"daily_budget_h":h,"contacts":len(contacts),
             "satellites_without_contact":len(alloc["diagnostics"]["coverage"]["satellites_without_contact"]),
             "reserved_h":round(sum(c["seconds"] for c in contacts)/3600,3),
             "useful_tx_h":round(sum(c["usable_seconds"] for c in contacts)/3600,3),
             "delivered_mbit":round(sum(v["delivered_bits_assuming_perfect_link"] for v in sats.values())/1e6,3),
             "max_peak_memory_mbit":round(max(v["peak_backlog_bits"] for v in sats.values())/1e6,3),
             "satellites_with_deadline_violations":violations,
             "all_deadlines_met":delivery["all_deadlines_met"],
             "coverage_feasibility":alloc["diagnostics"]["coverage"]["initial_feasibility"]}
        rows.append(row)
        details[str(h)]={"allocation":alloc["diagnostics"],"delivery":delivery}
    with (out/"sensitivity.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    result={"status":"HYPOTHETICAL_2020_GEOMETRY_SHIFTED_TO_2030_NOT_DSN_BOOKED",
            "horizon_start_utc":epoch.isoformat(),"horizon_end_utc":end.isoformat(),
            "gross_bps":rate,"overhead":overhead,"telemetry":"SEVEN_STREAM_ASSUMED",
            "pass_policy":pol,"cases":rows,"details":details,
            "conclusion":"NO_VERIFIED_FEASIBLE_DSN_REQUIREMENT" if not any(r["all_deadlines_met"] for r in rows)
                else "SCENARIO_ONLY_FEASIBILITY_NOT_DSN_BOOKING",
            "caveat":"Discrete sampled budgets do not prove a global minimum; even 24h/day cannot overcome geometry or minimum-pass duration."}
    (out/"sensitivity.json").write_text(json.dumps(result,indent=2,default=str)+"\n",encoding="utf-8")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(8,4))
        ax.plot([r["daily_budget_h"] for r in rows],
                [r["satellites_with_deadline_violations"] for r in rows],marker="o")
        ax.set(xlabel="Shared DSN budget (h/day)",ylabel="Satellites missing deadlines",
               title="SELENA DSN sensitivity — unverified visibility")
        ax.set_ylim(-0.5,8.5)
        fig.tight_layout();fig.savefig(out/"deadline_sensitivity.png",dpi=150);plt.close(fig)
    except ImportError:
        pass
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--hours",type=float,nargs="+",default=[1,3,6,12,24])
    p.add_argument("--output-dir",default="outputs/dsn_sensitivity")
    p.add_argument("--gross-bps",type=float)
    a=p.parse_args()
    r=run(a.hours,a.output_dir,a.gross_bps)
    print(json.dumps(r["cases"],indent=2))
