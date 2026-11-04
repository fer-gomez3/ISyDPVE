"""Run from repo root: python -m ttc.run_analysis [--downlink-bps 2000]."""
import argparse,json
from pathlib import Path
from .engineering_calculations import calculate
from .contact_analysis import load_contacts,candidate_schedule,summarize,write_csv,dt
from .storage_model import simulate

def run(contacts_path="data/contacts_master.csv",output_dir="outputs",downlink_bps=None,overhead=0.0):
    contacts=load_contacts(contacts_path)
    schedule=candidate_schedule(contacts)
    summary=summarize(contacts,schedule)
    base=calculate()
    rate=sum(x["rate_bps"] for x in base["telemetry"] if x["rate_bps"] is not None)
    start,end=dt(summary["epoch_start"]),dt(summary["epoch_end"])
    duration=(end-start).total_seconds()
    by_sat={}
    for row in summary["satellites"]:
        sat=row["satellite"]
        contacts_sat=[x for x in schedule if x["satellite"]==sat]
        usable=sum(x["seconds"] for x in contacts_sat)
        by_sat[sat]={**row,"known_generated_mbit_over_epoch":rate*duration/1e6,
            "ideal_required_net_bps_known_only":rate*duration/usable if usable else None,
            "storage":simulate(contacts_sat,start,end,rate,downlink_bps,overhead),
            "full_telemetry_total_unknown":bool(base["missing_rates"])}
    result={"geometric_contacts_source":contacts_path,
        "epoch_warning":"Historical 2020 geometry; not 2030 mission operations",
        "schedule":summary,"known_generation_bps":rate,
        "missing_telemetry_rates":base["missing_rates"],
        "downlink_bps_scenario":downlink_bps,"overhead_fraction_scenario":overhead,
        "by_satellite":by_sat,
        "interfaces":{"obdh":"storage.conservative_peak_buffer_mbit, known sources only",
            "ttc":"ideal_required_net_bps_known_only, ideal aggregate candidate contact time",
            "aocs":"candidate_dsn_schedule.csv, not a pointing command plan",
            "eps":"TX power and energy TBD until link budget and equipment are specified",
            "thermal":"TX heat TBD until transmitter DC and RF efficiencies are specified"}}
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    (output/"dsn_analysis.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    write_csv(output/"candidate_dsn_schedule.csv",schedule)
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--contacts",default="data/contacts_master.csv")
    p.add_argument("--downlink-bps",type=float)
    p.add_argument("--overhead",type=float,default=0.0)
    a=p.parse_args()
    r=run(a.contacts,downlink_bps=a.downlink_bps,overhead=a.overhead)
    print(json.dumps({"windows":r["schedule"]["geometric_windows"],
        "candidate_segments":r["schedule"]["candidate_segments"],
        "known_generation_bps":r["known_generation_bps"],
        "by_satellite":r["by_satellite"]},indent=2))
