"""Scenario-only DSN time allocation. Visibility is NOT a DSN booking."""
import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .contact_analysis import load_contacts, candidate_schedule

def allocate(contacts, policy):
    default=float(policy["default_fraction"])
    overrides=policy.get("station_fraction",{})
    sat_overrides=policy.get("satellite_fraction",{})
    setup=float(policy.get("setup_minutes",5))*60
    min_contact=float(policy.get("min_contact_minutes",15))*60
    if setup<0 or min_contact<0: raise ValueError("Times must be nonnegative")
    fractions=[default,*map(float,overrides.values()),*map(float,sat_overrides.values())]
    if any(not 0<=v<=1 for v in fractions): raise ValueError("Allocation fractions must be between 0 and 1")
    schedule=candidate_schedule(contacts)
    rows=[]
    daily_cap=policy.get("daily_network_hours")
    if daily_cap is not None and float(daily_cap)<0:raise ValueError("daily_network_hours must be nonnegative")
    used_by_day={}
    for w in sorted(schedule,key=lambda x:x["start"]):
        fraction=float(sat_overrides.get(w["satellite"],overrides.get(w["station"],default)))
        # Hypothetical allocation is a contiguous portion starting at the candidate interval start.
        allocated=w["seconds"]*fraction
        day=w["start"].date().isoformat()
        if daily_cap is not None:
            remaining=max(0,float(daily_cap)*3600-used_by_day.get(day,0))
            allocated=min(allocated,remaining)
        if allocated>=min_contact:
            used_by_day[day]=used_by_day.get(day,0)+allocated
        eligible=allocated>=min_contact
        useful=max(0,allocated-setup) if eligible else 0
        rows.append(dict(satellite=w["satellite"],station=w["station"],
            candidate_start_utc=w["start"].isoformat(),
            candidate_end_utc=w["end"].isoformat(),
            geometric_candidate_seconds=round(w["seconds"],3),
            allocation_fraction=fraction,
            assigned_seconds=round(allocated,3) if eligible else 0,
            useful_tx_seconds=round(useful,3),
            eligible=eligible,
            scenario_only=True))
    return rows

def compute_allocation(contacts_path="data/contacts_master.csv",
                       policy_path="data/dsn_allocation_scenario.json",
                       output_dir="outputs"):
    policy=json.loads(Path(policy_path).read_text(encoding="utf-8"))
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
        "allocation_note":"Fractions apply to conflict-resolved candidate intervals, not full overlapping visibility windows. Assigned portion is modeled at interval start; acquisition/setup subtracted. No real DSN reservation or slew constraints.",
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
