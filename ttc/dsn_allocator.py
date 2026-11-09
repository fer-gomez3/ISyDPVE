"""Conflict-free preliminary DSN resource allocation.

Visibility is not a DSN booking. Each station has one hypothetical resource,
with optional availability intervals. Contacts are whole windows, not arbitrary
tiny fragments. A schedule cannot prove mission 24h compliance if its horizon
is shorter than 24h or if actual DSN grants are unknown.
"""
from datetime import timedelta
from .contact_analysis import candidate_schedule

def allocate(contacts, availability=None, minimum_seconds=300, setup_seconds=0,
             station_capacity=None):
    if minimum_seconds<=0 or setup_seconds<0:
        raise ValueError("Invalid duration constraints")
    availability=availability or {}
    station_capacity=station_capacity or {}
    if any(v!=1 for v in station_capacity.values()):
        raise ValueError("Only one antenna resource per station is modeled")
    candidates=[]
    for c in contacts:
        if c["end"]<=c["start"]:
            raise ValueError("Invalid contact window")
        windows=availability.get(c["station"])
        spans=[(c["start"],c["end"])] if windows is None else [
            (max(c["start"],a),min(c["end"],b)) for a,b in windows]
        for a,b in spans:
            if (b-a).total_seconds()>=minimum_seconds+setup_seconds:
                candidates.append({**c,"start":a,"end":b,
                    "seconds":(b-a).total_seconds()})
    # Earliest end favors feasible complete contacts; least served satellite
    # breaks ties. This is a deterministic heuristic, not an optimal solver.
    allocated={c["satellite"]:0.0 for c in candidates}
    busy_by_station={};busy_by_sat={};selected=[]
    remaining=sorted(candidates,key=lambda c:(c["end"],c["start"],c["station"],c["satellite"]))
    for c in remaining:
        a,b=c["start"],c["end"]
        if any(a<x["end"] and b>x["start"] for x in busy_by_station.get(c["station"],[])):
            continue
        if any(a<x["end"] and b>x["start"] for x in busy_by_sat.get(c["satellite"],[])):
            continue
        row={"station":c["station"],"satellite":c["satellite"],
             "start":a,"end":b,"seconds":(b-a).total_seconds(),
             "usable_seconds":(b-a).total_seconds()-setup_seconds,
             "status":"HYPOTHETICAL_ALLOCATION_NOT_DSN_BOOKING"}
        selected.append(row)
        busy_by_station.setdefault(c["station"],[]).append(row)
        busy_by_sat.setdefault(c["satellite"],[]).append(row)
        allocated[c["satellite"]]+=row["usable_seconds"]
    return sorted(selected,key=lambda c:(c["start"],c["station"],c["satellite"]))

def verify_contacts(schedule, satellites, start, end, max_gap_hours=24):
    if end<=start or max_gap_hours<=0:
        raise ValueError("Invalid horizon or gap")
    results={}
    for sat in satellites:
        rows=sorted((c for c in schedule if c["satellite"]==sat),key=lambda c:c["start"])
        cursor=start;gaps=[]
        for c in rows:
            if c["start"]>cursor:
                gaps.append((c["start"]-cursor).total_seconds()/3600)
            cursor=max(cursor,c["end"])
        gaps.append(max(0,(end-cursor).total_seconds()/3600))
        maximum=max(gaps,default=0)
        results[sat]={"contacts":len(rows),"maximum_gap_hours":maximum,
            "meets_max_gap":maximum<=max_gap_hours,
            "status":"PRELIMINARY_GEOMETRIC_ALLOCATION_ONLY"}
    return results
