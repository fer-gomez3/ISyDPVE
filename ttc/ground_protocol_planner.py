"""SELENA ground-grant driven downlink protocol planning (scenario, not DSN bookings).

Input: stream generation rates, deadlines, candidate visibility and ground grants.
Output: requested contact cadence, granted useful time, required rate and delivery
feasibility. Acknowledgments are modeled as a configurable delivery efficiency,
NOT as a verified CCSDS implementation.
"""
import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

def utc(s):
    d=datetime.fromisoformat(str(s).replace("Z","+00:00"))
    if d.tzinfo is None: raise ValueError("UTC offset required")
    return d.astimezone(timezone.utc)

def load_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def plan(streams, windows, grants, *, utilization=0.5, overhead=0.2,
         setup_minutes=15, design_margin=0.2, epoch=None):
    if not 0 < utilization <= 1 or not 0 <= overhead < 1 or design_margin < 0:
        raise ValueError("Invalid utilization, overhead or margin")
    if setup_minutes < 0: raise ValueError("Negative setup")
    if not streams: raise ValueError("No streams")
    if not windows: raise ValueError("No visibility windows")
    stream_map={}
    for s in streams:
        name=s["name"]
        rate=float(s["rate_bps"])
        deadline=float(s["deadline_hours"])
        priority=int(s["priority"])
        if name in stream_map or rate<0 or deadline<=0 or priority not in range(1,6):
            raise ValueError("Invalid stream")
        stream_map[name]={"rate_bps":rate,"deadline_hours":deadline,"priority":priority}
    visible={}
    for w in windows:
        key=(w["satellite"],w["station"])
        a,b=utc(w["start_utc"]),utc(w["end_utc"])
        if b<=a: raise ValueError("Invalid visibility")
        visible.setdefault(key,[]).append((a,b))
    first=utc(epoch) if epoch else min(a for vals in visible.values() for a,_ in vals)
    requirements=[{"subsystem":name,"priority":s["priority"],
        "deadline_hours":s["deadline_hours"],"nominal_bits_per_deadline":s["rate_bps"]*s["deadline_hours"]*3600,
        "required_contacts_per_day_upper_bound":24/s["deadline_hours"]}
        for name,s in stream_map.items()]
    # Each grant is an externally supplied antenna allocation, never an inferred DSN booking.
    results=[]
    for g in sorted(grants,key=lambda x:x["start_utc"]):
        a,b=utc(g["start_utc"]),utc(g["end_utc"])
        sat,station=g["satellite"],g["station"]
        if b<=a: raise ValueError("Invalid grant")
        if not any(va<=a and b<=vb for va,vb in visible.get((sat,station),[])):
            raise ValueError("Grant outside supplied visibility: "+sat+" "+station)
        granted=(b-a).total_seconds()
        useful=max(0,granted*utilization-setup_minutes*60)
        if useful<=0:
            status="NO_USEFUL_TIME"
        else:
            status="PRELIMINARY_RATE_ONLY"
        # Demand at this contact: conservative accumulated data since scenario start
        # or previous granted contact end, capped by the stream's deadline horizon.
        previous=[r for r in results if r["satellite"]==sat]
        last=max((utc(r["end_utc"]) for r in previous),default=first)
        elapsed=max(0,(b-max(first,last)).total_seconds())
        demand=[]
        for name,s in stream_map.items():
            # No fake acknowledgments: nominal generation is assumed, and results
            # are requirements rather than proof of completed transfers.
            bits=s["rate_bps"]*elapsed
            due=last+timedelta(hours=s["deadline_hours"])
            demand.append({"subsystem":name,"priority":s["priority"],"bits":bits,
                           "deadline_utc":due.isoformat(),
                           "deadline_before_grant_end":due<=b})
        payload_bits=sum(x["bits"] for x in demand)
        required=payload_bits/useful/(1-overhead) if useful>0 else None
        results.append({"satellite":sat,"station":station,"start_utc":a.isoformat(),
                        "end_utc":b.isoformat(),"granted_seconds":granted,
                        "usable_seconds":useful,"nominal_payload_bits":payload_bits,
                        "required_gross_bps":required,"design_gross_bps":required*(1+design_margin) if required is not None else None,
                        "demand":demand,"status":status})
    # A separate hard-deadline check flags insufficient grant cadence even if
    # the nominal link rate could be arbitrarily high.
    satellites=sorted({w["satellite"] for w in windows})
    risks=[]
    end=max(b for vals in visible.values() for _,b in vals)
    for sat in satellites:
        passes=sorted((r for r in results if r["satellite"]==sat and r["usable_seconds"]>0),key=lambda r:r["end_utc"])
        for name,s in stream_map.items():
            cursor=first
            for r in passes:
                finish=utc(r["end_utc"])
                if finish-cursor>timedelta(hours=s["deadline_hours"]):
                    risks.append({"satellite":sat,"subsystem":name,"reason":"GRANT_GAP_EXCEEDS_DEADLINE",
                                  "gap_hours":(finish-cursor).total_seconds()/3600})
                cursor=finish
            if end-cursor>timedelta(hours=s["deadline_hours"]):
                risks.append({"satellite":sat,"subsystem":name,"reason":"END_OF_HORIZON_UNSERVED",
                              "gap_hours":(end-cursor).total_seconds()/3600})
    return {"status":"PRELIMINARY_NOT_DELIVERY_PROOF","geometry_status":"SUPPLIED_NOT_PROPAGATED",
            "ground_grants_status":"USER_SUPPLIED_NOT_CONFIRMED_DSN_BOOKINGS",
            "requirements":requirements,"contacts":results,"deadline_risks":risks,
            "maximum_design_gross_bps":max((r["design_gross_bps"] or 0 for r in results),default=0),
            "assumptions":{"visibility_utilization_fraction":utilization,"protocol_overhead_fraction":overhead,
                           "setup_minutes":setup_minutes,"design_margin_fraction":design_margin},
            "limitations":"Nominal demand only; no packet ACK/ARQ, partial-transfer state, RF link closure or time-varying generation. Cadence risks are conservative flags, not full feasibility proof."}

def run(streams_path,visibility_path,grants_path,output_path,
        utilization=0.5,overhead=0.2,setup_minutes=15,design_margin=0.2):
    streams=json.loads(Path(streams_path).read_text(encoding="utf-8"))
    if isinstance(streams,dict): streams=streams["streams"]
    result=plan(streams,load_csv(visibility_path),load_csv(grants_path),
                utilization=utilization,overhead=overhead,setup_minutes=setup_minutes,design_margin=design_margin)
    p=Path(output_path);p.parent.mkdir(parents=True,exist_ok=True)
    from .ground_delivery import size_rate
    result["deadline_rate_sizing"]=size_rate(streams,load_csv(visibility_path),load_csv(grants_path),
        utilization=utilization,overhead=overhead,setup_minutes=setup_minutes,
        max_bps=10000000,step_seconds=60)
    p.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--streams",default="data/downlink_streams_example.json")
    p.add_argument("--visibility",default="data/contacts_master.csv")
    p.add_argument("--grants",default="data/ground_grants_example.csv")
    p.add_argument("--output",default="outputs/ground_protocol_plan.json")
    p.add_argument("--utilization",type=float,default=0.5)
    p.add_argument("--overhead",type=float,default=0.2)
    p.add_argument("--setup-minutes",type=float,default=15)
    p.add_argument("--design-margin",type=float,default=0.2)
    a=p.parse_args()
    print(json.dumps(run(a.streams,a.visibility,a.grants,a.output,a.utilization,a.overhead,a.setup_minutes,a.design_margin),indent=2))
