"""Rank hypothetical DSN contact windows using link energy, backlog urgency and geometry.

Never infer 2030 range/elevation from shifted 2020 timestamps. Missing geometry
produces an explicitly unranked result, not a fabricated optimum.
PRELIMINARY DELIVERY NOTE:
The current worst-case window range and minimum elevation are suitable for
preliminary sizing/trade studies only. Outstanding work: elevation-dependent
atmospheric losses, time-resolved minimum link margin across each contact,
and real 2030 propagated satellite/ground-station geometry. Until those are
implemented, results are not a validated final HGA or transmitter design.

"""
import csv
import json
from pathlib import Path
from datetime import datetime, timezone
from ttc.link_budget import evaluate_link
from ttc.parameters import hga_link_defaults


def _utc(value):
    parsed=datetime.fromisoformat(str(value).replace("Z","+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Geometry timestamps must include UTC offset")
    return parsed.astimezone(timezone.utc)

def worst_case_geometry(window, geometry):
    """Worst measured range and elevation over a full scheduled interval.

    Accepts time-series rows keyed by (satellite, station, timestamp UTC).
    An interval is valid only if measured samples include both endpoints.
    Never silently extrapolate missing geometry.
    """
    start=_utc(window["candidate_start_utc"])
    end_key=window.get("candidate_end_utc") or window.get("end_utc")
    if not end_key:
        return None
    end=_utc(end_key)
    if end<=start:
        raise ValueError("Window end must follow start")
    sat,station=str(window["satellite"]),str(window["station"])
    samples=[]
    for (s,g,t),value in geometry.items():
        if str(s)!=sat or str(g)!=station:
            continue
        instant=_utc(t)
        if start<=instant<=end:
            samples.append((instant,value))
    samples.sort(key=lambda row:row[0])
    if not samples or samples[0][0]!=start or samples[-1][0]!=end:
        return None
    ranges=[float(v["distance_km"]) for _,v in samples]
    elevations=[float(v["elevation_deg"]) for _,v in samples]
    if any(d<=0 for d in ranges) or any(not 0<=e<=90 for e in elevations):
        raise ValueError("Invalid geometry sample")
    return {"distance_km":max(ranges),"elevation_deg":min(elevations),
            "geometry_sample_count":len(samples),
            "geometry_source":"SUPPLIED_INTERVAL_SAMPLES"}

def rank_windows(windows, geometry, link, urgency=None, scenario_defaults=None):
    urgency=urgency or {}
    scenario_defaults=scenario_defaults or {}
    ranked=[]
    for w in windows:
        item=dict(w)
        key=(str(w["satellite"]),str(w["station"]),str(w["candidate_start_utc"]))
        measured=worst_case_geometry(w,geometry)
        g=measured or scenario_defaults
        if not g or g.get("distance_km") is None or g.get("elevation_deg") is None:
            item.update(rank_status="MISSING_INTERVAL_GEOMETRY",energy_j_per_payload_bit=None,score=None)
            ranked.append(item)
            continue
        if not 0<=float(g["elevation_deg"])<=90:raise ValueError("Elevation outside 0..90 degrees")
        p=dict(link)
        p["distance_km"]=float(g["distance_km"])
        result=evaluate_link(p)
        if result["status"]!="PRELIMINARY":
            item.update(rank_status="MISSING_RF_INPUTS",energy_j_per_payload_bit=None,score=None)
            ranked.append(item)
            continue
        item["geometry_source"]="SUPPLIED_INTERVAL_SAMPLES" if measured else "NOMINAL_2030_SCENARIO"
        rate=float(p["data_rate_bps"])
        dc=result["estimated_tx_dc_w"]
        if dc is None:raise ValueError("PA efficiency and electronics power required")
        # Higher urgency reduces the cost of serving an older/critical backlog.
        priority=max(0,float(urgency.get(w["satellite"],0)))
        energy=dc/rate
        item.update(rank_status="PRELIMINARY_RANKED",distance_km=float(g["distance_km"]),
                    elevation_deg=float(g["elevation_deg"]),
                    minimum_tx_rf_w=result["minimum_tx_rf_w_with_design_margin"],
                    estimated_tx_dc_w=dc,energy_j_per_payload_bit=energy,
                    score=energy/(1+priority))
        ranked.append(item)
    return sorted(ranked,key=lambda x:(x["score"] is None,
                   float("inf") if x["score"] is None else x["score"]))

def load_geometry(path):
    if not path or not Path(path).exists():return {}
    with open(path,newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    return {(r["satellite"],r["station"],r["candidate_start_utc"]):r for r in rows}

def compute(windows_path="outputs/dsn_allocated_windows.csv",
            geometry_path="data/contact_geometry_2030.csv",
            link_path="data/link_budget_inputs.json",
            scenario_path="data/contact_nominal_2030_scenario.json",
            output_path="outputs/contact_energy_ranking.json"):
    with open(windows_path,newline="",encoding="utf-8") as f:
        windows=list(csv.DictReader(f))
    link=json.loads(Path(link_path).read_text(encoding="utf-8"))
    scenario=json.loads(Path(scenario_path).read_text(encoding="utf-8"))
    if scenario.get("enabled"):
        link={**scenario["link_assumptions"],**hga_link_defaults(),**{k:v for k,v in link.items() if v is not None}}
        defaults=scenario["geometry_assumptions"]
    else:
        defaults=None
    result=rank_windows(windows,load_geometry(geometry_path),link,scenario_defaults=defaults)
    summary={"status":"RANKED_PRELIMINARY" if result and all(x["score"] is not None for x in result)
             else "GEOMETRY_OR_RF_INPUTS_MISSING",
             "note":"Contact timestamps treated as 2030 scenario. Constant nominal range/elevation are placeholders, not propagated geometry; DSN availability and deadlines unverified.",
             "ranked_windows":result}
    out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    return summary

if __name__=="__main__":
    print(compute()["status"])
