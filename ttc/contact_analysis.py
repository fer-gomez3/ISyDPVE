"""Candidate DSN planning from geometric windows; NOT confirmed antenna bookings."""
import csv
from datetime import datetime
from pathlib import Path

def dt(s):
    return datetime.fromisoformat(s.replace("Z","+00:00"))

def load_contacts(path="data/contacts_master.csv"):
    with open(path,encoding="utf-8-sig",newline="") as f: rows=list(csv.DictReader(f))
    result=[]
    for r in rows:
        a,b=dt(r["start_utc"]),dt(r["end_utc"])
        if b<=a: raise ValueError("Invalid window "+r["contact_id"])
        result.append(dict(id=r["contact_id"],satellite=r["satellite"],station=r["station"],start=a,end=b,seconds=(b-a).total_seconds()))
    return sorted(result,key=lambda r:(r["start"],r["end"],r["id"]))

def candidate_schedule(contacts):
    """One hypothetical antenna per station and one link per satellite.
    Fairness heuristic minimizes cumulative assigned time. Ignores slew and acquisition.
    Segments can be too short to be operationally useful: NOT a DSN booking schedule.
    """
    if not contacts: return []
    times=sorted({t for c in contacts for t in (c["start"],c["end"])})
    stations=sorted({c["station"] for c in contacts})
    allocated={c["satellite"]:0.0 for c in contacts}
    out=[]
    for a,b in zip(times,times[1:]):
        seconds=(b-a).total_seconds()
        busy=set()
        for station in stations:
            options=[c for c in contacts if c["station"]==station and c["start"]<=a and c["end"]>=b and c["satellite"] not in busy]
            if not options: continue
            chosen=min(options,key=lambda c:(allocated[c["satellite"]],c["end"],c["satellite"]))
            sat=chosen["satellite"]
            busy.add(sat);allocated[sat]+=seconds
            out.append(dict(station=station,satellite=sat,start=a,end=b,seconds=seconds))
    # Merge adjacent intervals of the same station/satellite.
    merged=[]
    for c in sorted(out,key=lambda x:(x["station"],x["satellite"],x["start"])):
        if merged and merged[-1]["station"]==c["station"] and merged[-1]["satellite"]==c["satellite"] and merged[-1]["end"]==c["start"]:
            merged[-1]["end"]=c["end"];merged[-1]["seconds"]+=c["seconds"]
        else: merged.append(c.copy())
    return sorted(merged,key=lambda x:(x["start"],x["station"]))

def summarize(contacts,schedule):
    start=min(x["start"] for x in contacts)
    end=max(x["end"] for x in contacts)
    sats=sorted({x["satellite"] for x in contacts})
    rows=[]
    for sat in sats:
        original=[x for x in contacts if x["satellite"]==sat]
        assigned=sorted([x for x in schedule if x["satellite"]==sat],key=lambda x:x["start"])
        cursor=start;gaps=[]
        for x in assigned:
            if x["start"]>cursor:gaps.append((x["start"]-cursor).total_seconds())
            cursor=max(cursor,x["end"])
        gaps.append((end-cursor).total_seconds())
        rows.append(dict(satellite=sat,geometric_windows=len(original),
            geometric_hours=sum(x["seconds"] for x in original)/3600,
            candidate_hours=sum(x["seconds"] for x in assigned)/3600,
            max_gap_hours=max(gaps)/3600,
            candidate_segments=len(assigned)))
    return dict(epoch_start=start.isoformat(),epoch_end=end.isoformat(),
        duration_hours=(end-start).total_seconds()/3600,
        geometric_windows=len(contacts),candidate_segments=len(schedule),satellites=rows,
        disclaimer="2020 geometric data, not 2030 operational DSN allocations. One hypothetical station resource; no acquisition/slew constraints.")

def write_csv(path,schedule):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.writer(f);w.writerow(["satellite","station","start_utc","end_utc","duration_s"])
        for x in schedule:w.writerow([x["satellite"],x["station"],x["start"].isoformat(),x["end"].isoformat(),round(x["seconds"],3)])
