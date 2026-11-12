"""Generate ground-segment contact requests from subsystem delivery deadlines.

Requests are planning proposals, never actual DSN reservations. Each request
includes a latest finish, nominal demand, requested usable time, and candidate
visibility intersections. Grant negotiation remains external.
"""
import csv
import json
from datetime import timedelta
from pathlib import Path
from .ground_protocol_planner import utc, load_csv

def propose(streams, windows, *, gross_bps, overhead=0.2,
            setup_minutes=15, utilization=0.5, start_utc=None, end_utc=None):
    if gross_bps<=0 or not 0<=overhead<1 or not 0<utilization<=1 or setup_minutes<0:
        raise ValueError("Invalid communication assumptions")
    if not streams or not windows:raise ValueError("Streams and windows required")
    starts=[utc(w["start_utc"]) for w in windows]
    ends=[utc(w["end_utc"]) for w in windows]
    start=utc(start_utc) if start_utc else min(starts)
    end=utc(end_utc) if end_utc else max(ends)
    if end<=start:raise ValueError("Invalid planning horizon")
    sats=sorted({w["satellite"] for w in windows})
    requests=[]
    # The most frequent stream determines baseline cadence; lower priorities
    # are aggregated into the same opportunity.
    cadence=min(float(s["deadline_hours"]) for s in streams)
    if cadence<=0 or any(float(s["rate_bps"])<0 or int(s["priority"]) not in range(1,6) for s in streams):
        raise ValueError("Invalid stream")
    total_rate=sum(float(s["rate_bps"]) for s in streams)
    index=0
    for sat in sats:
        due=start+timedelta(hours=cadence)
        previous=start
        while due<=end:
            bits=total_rate*(due-previous).total_seconds()
            tx=bits/(gross_bps*(1-overhead))
            granted=(tx+setup_minutes*60)/utilization
            candidates=[]
            for w in windows:
                if w["satellite"]!=sat:continue
                a,b=utc(w["start_utc"]),utc(w["end_utc"])
                if a>=due or b<=previous:continue
                available_start=max(a,previous)
                available_end=min(b,due)
                if (available_end-available_start).total_seconds()>=granted:
                    candidates.append({"station":w["station"],"earliest_start_utc":available_start.isoformat(),
                        "latest_end_utc":available_end.isoformat(),"available_seconds":(available_end-available_start).total_seconds()})
            requests.append({"request_id":f"REQ-{sat}-{index:04d}","satellite":sat,
                "earliest_start_utc":previous.isoformat(),"latest_finish_utc":due.isoformat(),
                "nominal_payload_bits":bits,"requested_grant_seconds":granted,
                "candidate_windows":candidates,"status":"CANDIDATE_AVAILABLE" if candidates else "NO_SINGLE_WINDOW_LONG_ENOUGH"})
            index+=1
            previous=due
            due+=timedelta(hours=cadence)
    return {"status":"REQUESTS_NOT_GROUND_GRANTS","requests":requests,
            "limitations":"Simple periodic requests, constant generation, one window per batch; no multi-window splitting, per-stream dynamic backlog, station competition or real DSN negotiation."}

def run(streams_path="data/downlink_streams_example.json",
        visibility_path="data/contacts_master.csv",
        output_path="outputs/ground_contact_requests.json",**kwargs):
    streams=json.loads(Path(streams_path).read_text(encoding="utf-8"))
    if isinstance(streams,dict):streams=streams["streams"]
    result=propose(streams,load_csv(visibility_path),**kwargs)
    path=Path(output_path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--streams",default="data/downlink_streams_example.json")
    p.add_argument("--visibility",default="data/contacts_master.csv")
    p.add_argument("--output",default="outputs/ground_contact_requests.json")
    p.add_argument("--gross-bps",type=float,default=256000)
    a=p.parse_args()
    print(json.dumps(run(a.streams,a.visibility,a.output,gross_bps=a.gross_bps),indent=2))
