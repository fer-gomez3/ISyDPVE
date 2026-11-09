"""Generate OBDH time-series CSV and PNG from existing DSN candidate schedule.

Run: python -m ttc.obdh_report --downlink-bps 256000
Illustrative scenario; not a certified DSN allocation or full telemetry budget.
"""
import argparse
import csv
import json
from pathlib import Path
from .contact_analysis import load_contacts,candidate_schedule,dt
from .engineering_calculations import calculate
from .obdh_timeline import timeline

def run(contacts_path="data/contacts_master.csv",output_dir="outputs/obdh",
        downlink_bps=256000,overhead=0.2,step_seconds=60):
    contacts=load_contacts(contacts_path)
    if not contacts:
        raise ValueError("No geometric contact windows")
    schedule=candidate_schedule(contacts)
    start=min(c["start"] for c in contacts)
    end=max(c["end"] for c in contacts)
    base=calculate()
    known_rate=sum(x["rate_bps"] for x in base["telemetry"] if x["rate_bps"] is not None)
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    summary={"scope":"known telemetry only, preliminary historical DSN candidate schedule",
             "missing_rates":base["missing_rates"],"satellites":{}}
    for sat in sorted({c["satellite"] for c in contacts}):
        assigned=[c for c in schedule if c["satellite"]==sat]
        result=timeline(assigned,start,end,known_rate,downlink_bps,overhead,step_seconds)
        with (out/f"{sat}_timeline.csv").open("w",newline="",encoding="utf-8") as f:
            writer=csv.DictWriter(f,fieldnames=list(result["rows"][0]))
            writer.writeheader();writer.writerows(result["rows"])
        summary["satellites"][sat]={k:v for k,v in result.items() if k!="rows"}
    (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        summary["plot_status"]="MATPLOTLIB_NOT_INSTALLED"
    else:
        for sat in summary["satellites"]:
            with (out/f"{sat}_timeline.csv").open(newline="",encoding="utf-8") as f:
                rows=list(csv.DictReader(f))
            times=[dt(r["time_utc"]) for r in rows]
            fig,ax=plt.subplots(figsize=(11,4))
            ax.plot(times,[float(r["buffer_mbit"]) for r in rows],label="On-board buffer (Mbit)")
            ax.plot(times,[float(r["downlinked_cumulative_mbit"]) for r in rows],label="Downlinked cumulative (Mbit)")
            ax.set(xlabel="UTC",ylabel="Mbit",title=f"SELENA {sat}: OBDH scenario")
            ax.legend();fig.autofmt_xdate();fig.tight_layout()
            fig.savefig(out/f"{sat}_timeline.png",dpi=150);plt.close(fig)
        summary["plot_status"]="GENERATED"
        (out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    return summary

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--contacts",default="data/contacts_master.csv")
    parser.add_argument("--output-dir",default="outputs/obdh")
    parser.add_argument("--downlink-bps",type=float,default=256000)
    parser.add_argument("--overhead",type=float,default=0.2)
    args=parser.parse_args()
    print(json.dumps(run(args.contacts,args.output_dir,args.downlink_bps,args.overhead),indent=2))
