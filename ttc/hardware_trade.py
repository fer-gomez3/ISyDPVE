"""Compare preliminary SELENA storage requirement with documented OBC products.
Run: python -m ttc.hardware_trade
Does not certify products for lunar flight. Never treats RAM as persistent storage.
"""
import csv
import json
from pathlib import Path
from .adaptive_storage import ROOT

def compare(sizing_path=None, catalog_path=None, output_dir=None):
    sizing=json.loads(Path(sizing_path or ROOT/"outputs"/"memory_sizing.json").read_text(encoding="utf-8"))
    catalog=json.loads(Path(catalog_path or ROOT/"data"/"obdh_hardware_catalog.json").read_text(encoding="utf-8"))
    required=sizing["minimum_tested_storage_feasible_mbit"]
    fully=sizing["minimum_tested_all_constraints_pass_mbit"]
    rows=[]
    for p in catalog["products"]:
        # Nominal installed memory only. Redundancy/ECC/EDAC not specified consistently.
        nominal=p["capacity_mbit"]
        rows.append({"id":p["id"],"manufacturer":p["manufacturer"],"model":p["model"],
          "nominal_storage_mbit":nominal,"nominal_storage_MB":nominal/8,
          "required_storage_mbit":required,"nominal_capacity_pass":required is not None and nominal>=required,
          "all_mission_constraints_pass":fully is not None and nominal>=fully,
          "mass_kg_entire_obc":p["mass_kg"],"power_w_entire_obc":p["power_w"],
          "dimensions_mm_entire_obc":"x".join(str(x) if x is not None else "unknown" for x in p["dimensions_mm"]),
          "nominal_capacity_margin_ratio":round(nominal/required,3) if required else None,
          "qualification":p["qualification"],"source":p["source"],
          "selection_status":"CANDIDATE_ONLY_NOT_LUNAR_QUALIFIED",
          "storage_architecture":p["capacity_type"]})
    out=Path(output_dir or ROOT/"outputs");out.mkdir(parents=True,exist_ok=True)
    with (out/"obdh_hardware_trade.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    result={"minimum_tested_storage_feasible_mbit":required,
      "minimum_tested_all_constraints_pass_mbit":fully,
      "warning":"Capacity alone cannot validate 10-year lunar mission, ECC, radiation, endurance, redundancy or available power. Nominal capacity may not equal usable capacity.",
      "products":rows}
    (out/"obdh_hardware_trade.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result

if __name__=="__main__":
    result=compare()
    print(json.dumps({"required_mbit":result["minimum_tested_storage_feasible_mbit"],"candidates":len(result["products"])},indent=2))
