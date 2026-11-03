"""Run OBDH memory/DSN trade studies without assuming a fixed hardware capacity.

From repository root: python -m ttc.memory_sizing
Each scenario is an independent replay of the same shifted-2020 contact geometry.
"""
import csv
import json
import tempfile
from copy import deepcopy
from pathlib import Path
from .adaptive_storage import ROOT, plan

def trade_study(config_path=None, output_dir=None):
    base_path=Path(config_path or ROOT/"data"/"adaptive_storage_scenario.json")
    base=json.loads(base_path.read_text(encoding="utf-8"))
    original=json.loads((ROOT/"data"/"ttc_parameters.json").read_text(encoding="utf-8"))
    # DSN hours remain a central parameter; run memory sizing for the selected
    # budget rather than silently mutating global project configuration.
    capacities=[128,256,512,1024,2048,4096,8192]
    rows=[]
    with tempfile.TemporaryDirectory() as temp:
        for capacity in capacities:
            scenario=deepcopy(base)
            scenario["memory_capacity_mbit_per_satellite"]=capacity
            path=Path(temp)/"scenario.json"
            path.write_text(json.dumps(scenario),encoding="utf-8")
            r=plan(config_path=path,output_dir=Path(temp)/"run")
            for sat,v in r["satellites"].items():
                warnings=v["warnings"]
                rows.append({"capacity_mbit":capacity,"satellite":sat,
                             "orbital_group":sat.split("_")[1][0],
                             "peak_memory_mbit":v["peak_memory_mbit"],
                             "peak_occupancy_fraction":v["peak_occupancy_fraction"],
                             "downlinked_mbit":v["downlinked_mbit"],
                             "remaining_mbit":v["remaining_mbit"],
                             "contacts":v["contacts"],
                             "storage_feasible":not any(x in warnings for x in
                                 ("MEMORY_OVERFLOW","MEMORY_RESERVE_EXCEEDED")),
                             "all_constraints_pass":len(warnings)==0,
                             "warnings":";".join(warnings)})
    per_capacity=[]
    for capacity in capacities:
        subset=[x for x in rows if x["capacity_mbit"]==capacity]
        per_capacity.append({"capacity_mbit":capacity,
             "all_storage_feasible":all(x["storage_feasible"] for x in subset),
             "all_requirements_pass":all(x["all_constraints_pass"] for x in subset),
             "max_peak_mbit":max(x["peak_memory_mbit"] for x in subset),
             "total_contacts":sum(x["contacts"] for x in subset)})
    storage_options=[x["capacity_mbit"] for x in per_capacity if x["all_storage_feasible"]]
    fully_feasible=[x["capacity_mbit"] for x in per_capacity if x["all_requirements_pass"]]
    result={"status":"PRELIMINARY_SENSITIVITY_NOT_HARDWARE_SELECTION",
        "dsn_daily_network_hours_assumed":original["dsn_daily_network_hours"],
        "memory_reserve_fraction":base["memory_reserve_fraction"],
        "tested_capacity_mbit":capacities,
        "minimum_tested_storage_feasible_mbit":min(storage_options) if storage_options else None,
        "minimum_tested_all_constraints_pass_mbit":min(fully_feasible) if fully_feasible else None,
        "note":"Discrete sweep, NOT a mathematical minimum. 24h/age feasibility may be impossible for any capacity under assumed DSN availability. Age warnings are approximate; no real DSN reservations.",
        "per_capacity":per_capacity,"per_satellite":rows}
    out=Path(output_dir or ROOT/"outputs");out.mkdir(parents=True,exist_ok=True)
    (out/"memory_sizing.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    with (out/"memory_sizing.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    return result

if __name__=="__main__":
    r=trade_study()
    print(json.dumps({k:v for k,v in r.items() if k!="per_satellite"},indent=2))
