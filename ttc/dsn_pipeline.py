"""Preliminary end-to-end DSN scheduling and OBDH report.

Run: python -m ttc.dsn_pipeline --downlink-bps 256000
No DSN bookings or unknown telemetry rates are fabricated.
"""
import argparse,csv,json
from pathlib import Path
from .contact_analysis import load_contacts,write_csv
from .dsn_allocator import allocate,verify_contacts
from .engineering_calculations import calculate
from .obdh_timeline import timeline
from .telemetry_generation import calculate as calculate_channels, apply_computed_rates
from .transfer_planning import stream_requirements

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CONTACTS=str(ROOT/"data"/"contacts_master.csv")

def run(contacts_path=DEFAULT_CONTACTS,output_dir="outputs/dsn_pipeline",
        downlink_bps=256000,overhead=0.2,minimum_contact_seconds=300,
        setup_seconds=0,availability=None,telemetry_profile="confirmed"):
    contacts=load_contacts(contacts_path)
    if not contacts:
        raise ValueError("No input windows")
    start=min(c["start"] for c in contacts);end=max(c["end"] for c in contacts)
    schedule=allocate(contacts,availability,minimum_contact_seconds,setup_seconds)
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
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    write_csv(out/"candidate_schedule.csv",schedule)
    result={"status":"PRELIMINARY_NOT_DSN_BOOKED","source":str(contacts_path),
        "known_generation_bps":confirmed_rate,"modeled_generation_bps":known,
        "telemetry_profile":telemetry_profile,"scenario_streams":scenario_streams,
        "scenario_warning":"ASSUMED_RATES_NOT_CONFIRMED" if scenario_streams is not None else None,
        "missing_rates":rates["missing_rates"],
        "scenario_downlink_gross_bps":downlink_bps,"overhead_fraction":overhead,
        "setup_seconds_per_contact":setup_seconds,
        "contact_gaps":verify_contacts(schedule,sats,start,end),
        "satellites":{}}
    for sat in sats:
        assigned=[c for c in schedule if c["satellite"]==sat]
        # Setup time is excluded from transmission by shifting the beginning.
        useful=[{**c,"start":c["start"]+__import__("datetime").timedelta(seconds=setup_seconds)}
                for c in assigned if c["usable_seconds"]>0]
        t=timeline(useful,start,end,known,downlink_bps,overhead)
        with (out/f"{sat}_obdh.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(t["rows"][0]))
            w.writeheader();w.writerows(t["rows"])
        result["satellites"][sat]={k:v for k,v in t.items() if k!="rows"}
    (out/"summary.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--contacts",default=DEFAULT_CONTACTS)
    p.add_argument("--output-dir",default="outputs/dsn_pipeline")
    p.add_argument("--downlink-bps",type=float,default=256000)
    p.add_argument("--overhead",type=float,default=0.2)
    p.add_argument("--minimum-contact-seconds",type=float,default=300)
    p.add_argument("--setup-seconds",type=float,default=0)
    p.add_argument("--telemetry-profile",choices=["confirmed","scenario"],default="confirmed")
    a=p.parse_args()
    print(json.dumps(run(a.contacts,a.output_dir,a.downlink_bps,a.overhead,
                         a.minimum_contact_seconds,a.setup_seconds,telemetry_profile=a.telemetry_profile),indent=2))
