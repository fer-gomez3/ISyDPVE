"""Deterministic per-satellite backlog and priority downlink simulation.

Uses hypothetical allocated windows, not confirmed DSN bookings. Continuous generation
between events; prioritizes streams by priority and then age deadline. Backlog is
tracked in bits; deadlines are checked conservatively using oldest undelivered bit.
"""
import csv
import json
from datetime import datetime, timedelta
from pathlib import Path
from .contact_analysis import load_contacts
from .dsn_allocation import allocate
from .transfer_planning import stream_requirements

def run(cfg,contacts,policy):
    rows=allocate(contacts,policy)
    overhead=float(cfg["policy"]["protocol_overhead_fraction"])
    rate=cfg["policy"].get("net_downlink_bps")
    if rate is None: return {"status":"MISSING_DOWNLINK_RATE","contacts":[],"satellites":{}}
    rate=float(rate)
    if rate<=0 or not 0<=overhead<1:raise ValueError("Invalid downlink rate/overhead")
    effective=rate*(1-overhead)
    streams=stream_requirements(cfg)
    if any(s["mean_rate_bps"] is None for s in streams):raise ValueError("Unknown telemetry rate")
    start=min(c["start"] for c in contacts);end=max(c["end"] for c in contacts)
    satellites={}
    log=[]
    for sat in sorted({c["satellite"] for c in contacts}):
        backlog={s["name"]:0. for s in streams}
        oldest={s["name"]:None for s in streams}
        produced={s["name"]:0. for s in streams}
        sent={s["name"]:0. for s in streams}
        deadline_violations=set()
        peak=0.
        cursor=start
        windows=sorted((w for w in rows if w["satellite"]==sat and w["useful_tx_seconds"]>0),key=lambda w:w["candidate_start_utc"])
        def generate(until):
            nonlocal cursor,peak
            dt=(until-cursor).total_seconds()
            if dt< -1e-6:raise ValueError("Overlapping candidate windows for same satellite")
            for s in streams:
                name=s["name"];bits=s["mean_rate_bps"]*max(0,dt)
                if bits>0 and backlog[name]==0:oldest[name]=cursor
                backlog[name]+=bits;produced[name]+=bits
                if oldest[name] is not None and (until-oldest[name]).total_seconds()>s["deadline_hours"]*3600:
                    deadline_violations.add(name)
            peak=max(peak,sum(backlog.values()));cursor=until
        for w in windows:
            a=datetime.fromisoformat(w["candidate_start_utc"])
            # Assumes allocated block starts at candidate start; setup occurs before downlink.
            setup=float(policy.get("setup_minutes",5))*60
            tx_start=a+timedelta(seconds=setup)
            tx_end=tx_start+timedelta(seconds=w["useful_tx_seconds"])
            generate(tx_start)
            capacity=w["useful_tx_seconds"]*effective
            before=sum(backlog.values())
            used=0.
            for s in sorted(streams,key=lambda x:(-x["priority"],x["deadline_hours"],x["name"])):
                name=s["name"];take=min(backlog[name],capacity-used)
                backlog[name]-=take;sent[name]+=take;used+=take
                if backlog[name]<1e-7:backlog[name]=0.;oldest[name]=None
                if used>=capacity:break
            # Generate concurrently during transmission; conservative (not sent in same pass).
            generate(tx_end)
            log.append({"satellite":sat,"station":w["station"],"start_utc":tx_start.isoformat(),
                        "end_utc":tx_end.isoformat(),"useful_seconds":w["useful_tx_seconds"],
                        "capacity_mbit":capacity/1e6,"downloaded_mbit":used/1e6,
                        "backlog_before_mbit":before/1e6,"backlog_after_mbit":sum(backlog.values())/1e6})
        generate(end)
        satellites[sat]={"generated_mbit":sum(produced.values())/1e6,
            "downloaded_mbit":sum(sent.values())/1e6,
            "remaining_mbit":sum(backlog.values())/1e6,
            "peak_backlog_mbit":peak/1e6,
            "deadline_risk_streams":sorted(deadline_violations),
            "by_stream":{s["name"]:{"generated_mbit":produced[s["name"]]/1e6,
                "downloaded_mbit":sent[s["name"]]/1e6,
                "remaining_mbit":backlog[s["name"]]/1e6} for s in streams}}
    return {"status":"HYPOTHETICAL_SCENARIO","rate_bps":rate,"effective_data_bps":effective,
            "note":"Historical 2020 geometry; not DSN booked. Deadlines are conservative flags, not exact packet-age proof. No event bursts or slew model. Transmission during a window uses backlog available at its start.",
            "contacts":log,"satellites":satellites}

def compute(telemetry_path="data/telemetry_detailed_scenario.json",
            contacts_path="data/contacts_master.csv",
            policy_path="data/dsn_allocation_scenario.json",output_dir="outputs"):
    cfg=json.loads(Path(telemetry_path).read_text(encoding="utf-8"))
    policy=json.loads(Path(policy_path).read_text(encoding="utf-8"))
    result=run(cfg,load_contacts(contacts_path),policy)
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"downlink_simulation.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    if result["contacts"]:
        with (out/"downlink_contacts.csv").open("w",newline="",encoding="utf-8") as f:
            w=csv.DictWriter(f,fieldnames=list(result["contacts"][0]));w.writeheader();w.writerows(result["contacts"])
    return result

if __name__=="__main__":
    print(json.dumps(compute(),indent=2))
