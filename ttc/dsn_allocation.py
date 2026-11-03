"""Scenario-only DSN time allocation. Visibility is NOT a DSN booking."""
import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .contact_analysis import load_contacts, candidate_schedule
from .parameters import apply_policy

def allocate(contacts, policy):
    """Fair, capacity-limited allocation of hypothetical DSN time to the satellites.

    Candidate segments come from contact_analysis.candidate_schedule (one link per satellite,
    one antenna per station). Allocation is contiguous from each segment start. If the policy
    has a daily network cap (hours, shared by ALL satellites), each UTC day is filled with
    max-min fairness: the satellite with the least assigned time so far is served next, in
    one-minute increments, and a satellite with no usable segment simply gets nothing. No
    contact is created and no service is guaranteed. Setup time counts against the cap.
    """
    default=float(policy["default_fraction"])
    overrides=policy.get("station_fraction",{})
    sat_overrides=policy.get("satellite_fraction",{})
    setup=float(policy.get("setup_minutes",5))*60
    min_contact=float(policy.get("min_contact_minutes",15))*60
    if setup<0 or min_contact<0: raise ValueError("Times must be nonnegative")
    if min_contact<=setup: raise ValueError("min_contact_minutes must exceed setup_minutes, otherwise a contact carries no data")
    fractions=[default,*map(float,overrides.values()),*map(float,sat_overrides.values())]
    if any(not 0<=v<=1 for v in fractions): raise ValueError("Allocation fractions must be between 0 and 1")
    daily_cap=policy.get("daily_network_hours")
    if daily_cap is not None and float(daily_cap)<0:raise ValueError("daily_network_hours must be nonnegative")
    schedule=sorted(candidate_schedule(contacts),key=lambda x:(x["start"],x["station"],x["satellite"]))
    segments=[]
    for w in schedule:
        fraction=float(sat_overrides.get(w["satellite"],overrides.get(w["station"],default)))
        segments.append(dict(w=w,fraction=fraction,offered=w["seconds"]*fraction,allocated=0.0))
    by_day={}
    for seg in segments:
        by_day.setdefault(seg["w"]["start"].date().isoformat(),[]).append(seg)
    step=60.0
    for day,segs in by_day.items():
        if daily_cap is None:
            for seg in segs:
                if seg["offered"]>=min_contact: seg["allocated"]=seg["offered"]
            continue
        cap_left=float(daily_cap)*3600
        assigned={}
        sats=sorted({seg["w"]["satellite"] for seg in segs})
        while cap_left>1e-9:
            best=None
            for sat in sats:
                mine=[x for x in segs if x["w"]["satellite"]==sat]
                started=[x for x in mine if x["allocated"]>0 and x["offered"]-x["allocated"]>1e-9]
                fresh=[x for x in mine if x["allocated"]==0 and x["offered"]>=min_contact and cap_left>=min_contact]
                if not started and not fresh: continue
                key=(assigned.get(sat,0.0),sat)
                if best is None or key<best[0]:
                    best=(key,sat,started,fresh)
            if best is None: break
            _,sat,started,fresh=best
            if started:
                seg=max(started,key=lambda x:x["offered"]-x["allocated"])
                add=min(step,seg["offered"]-seg["allocated"],cap_left)
            else:
                seg=max(fresh,key=lambda x:x["offered"])
                add=min(min_contact,seg["offered"],cap_left)
            seg["allocated"]+=add;assigned[sat]=assigned.get(sat,0.0)+add;cap_left-=add
    rows=[]
    for seg in segments:
        w=seg["w"];allocated=seg["allocated"]
        eligible=allocated>=min_contact
        useful=max(0,allocated-setup) if eligible else 0
        rows.append(dict(satellite=w["satellite"],station=w["station"],
            candidate_start_utc=w["start"].isoformat(),
            candidate_end_utc=w["end"].isoformat(),
            geometric_candidate_seconds=round(w["seconds"],3),
            allocation_fraction=seg["fraction"],
            assigned_seconds=round(allocated,3) if eligible else 0,
            useful_tx_seconds=round(useful,3),
            eligible=eligible,
            scenario_only=True))
    return rows

def compute_allocation(contacts_path="data/contacts_master.csv",
                       policy_path="data/dsn_allocation_scenario.json",
                       output_dir="outputs"):
    policy=apply_policy(json.loads(Path(policy_path).read_text(encoding="utf-8")))
    contacts=load_contacts(contacts_path)
    rows=allocate(contacts,policy)
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    with (out/"dsn_allocated_windows.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else [
            "satellite","station","candidate_start_utc","candidate_end_utc",
            "geometric_candidate_seconds","allocation_fraction",
            "assigned_seconds","useful_tx_seconds","eligible","scenario_only"])
        writer.writeheader();writer.writerows(rows)
    result={"status":"HYPOTHETICAL_NOT_BOOKED",
        "geometry_note":"Contact geometry is a hypothetical input; 2030 timestamps may be calendar-shifted, NOT physically repropagated.",
        "allocation_note":"Fair (max-min) daily sharing of the assumed network hours among all satellites with available contacts. Fractions apply to conflict-resolved candidate intervals, not full overlapping visibility windows. Assigned portion is modeled at interval start; acquisition/setup subtracted. No real DSN reservation or slew constraints; no service is guaranteed.",
        "policy":policy,"daily_network_hours_limit":policy.get("daily_network_hours"),"candidate_segments":len(rows),
        "eligible_segments":sum(r["eligible"] for r in rows),
        "total_candidate_hours":sum(r["geometric_candidate_seconds"] for r in rows)/3600,
        "total_assigned_hours":sum(r["assigned_seconds"] for r in rows)/3600,
        "total_useful_hours":sum(r["useful_tx_seconds"] for r in rows)/3600,
        "by_satellite":{}}
    for sat in sorted({r["satellite"] for r in rows}):
        subset=[r for r in rows if r["satellite"]==sat]
        result["by_satellite"][sat]={
            "candidate_hours":sum(r["geometric_candidate_seconds"] for r in subset)/3600,
            "assigned_hours":sum(r["assigned_seconds"] for r in subset)/3600,
            "useful_hours":sum(r["useful_tx_seconds"] for r in subset)/3600}
    (out/"dsn_allocation_summary.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--contacts",default="data/contacts_master.csv")
    p.add_argument("--policy",default="data/dsn_allocation_scenario.json")
    p.add_argument("--output-dir",default="outputs")
    a=p.parse_args()
    print(json.dumps(compute_allocation(a.contacts,a.policy,a.output_dir),indent=2))
