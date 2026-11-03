"""Rank hypothetical DSN contact windows using link energy, backlog urgency and geometry.

Never infer 2030 range/elevation from shifted 2020 timestamps. Missing geometry
produces an explicitly unranked result, not a fabricated optimum.
"""
import csv
import json
from pathlib import Path
from ttc.link_budget import evaluate_link

def rank_windows(windows, geometry, link, urgency=None):
    urgency=urgency or {}
    ranked=[]
    for w in windows:
        item=dict(w)
        key=(str(w["satellite"]),str(w["station"]),str(w["candidate_start_utc"]))
        g=geometry.get(key)
        if not g or g.get("distance_km") is None or g.get("elevation_deg") is None:
            item.update(rank_status="MISSING_2030_GEOMETRY",energy_j_per_payload_bit=None,score=None)
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
            output_path="outputs/contact_energy_ranking.json"):
    with open(windows_path,newline="",encoding="utf-8") as f:
        windows=list(csv.DictReader(f))
    link=json.loads(Path(link_path).read_text(encoding="utf-8"))
    result=rank_windows(windows,load_geometry(geometry_path),link)
    summary={"status":"RANKED_PRELIMINARY" if result and all(x["score"] is not None for x in result)
             else "GEOMETRY_OR_RF_INPUTS_MISSING",
             "note":"Ranking is advisory. DSN booking, contact conflicts, data deadlines and actual 2030 ephemerides must be validated.",
             "ranked_windows":result}
    out=Path(output_path);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    return summary

if __name__=="__main__":
    print(compute()["status"])
