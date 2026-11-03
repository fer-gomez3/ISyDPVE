"""SELENA communications pipeline. Run from repository root: python main.py

Optional scenario: python main.py --link-input data/link_budget_inputs.json
"""
import argparse
import json
from pathlib import Path
from ttc.engineering_calculations import calculate
from ttc.transfer_planning import compute, load_requirements
from ttc.power_budget import evaluate
from ttc.link_budget import from_file as evaluate_link

def main():
    parser=argparse.ArgumentParser(description="SELENA TT&C / OBDH engineering overview")
    parser.add_argument("--requirements",default="data/transfer_requirements.json")
    parser.add_argument("--contacts",default="data/contacts_master.csv")
    parser.add_argument("--link-input",default="data/link_budget_inputs.json")
    parser.add_argument("--output-dir",default="outputs")
    args=parser.parse_args()
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    requirements=load_requirements(args.requirements)
    link=json.loads(Path(args.link_input).read_text(encoding="utf-8"))
    # Keep the original engineering reference and the editable planning model distinct.
    engineering=calculate()
    (out/"subsystem_interfaces.json").write_text(json.dumps(engineering,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    power=evaluate(link)
    (out/"power_budget.json").write_text(json.dumps(power,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    rf_link=evaluate_link(args.link_input)
    (out/"link_budget.json").write_text(json.dumps(rf_link,indent=2)+"\n",encoding="utf-8")
    summary={"link_budget":"outputs/link_budget.json","link_status":rf_link["status"],"engineering":"outputs/subsystem_interfaces.json",
             "power":"outputs/power_budget.json",
             "power_status":power["status"],"power_missing_inputs":power["missing_inputs"]}
    if Path(args.contacts).exists():
        planning=compute(requirements,contacts_path=args.contacts,output_dir=args.output_dir)
        summary.update(planning="outputs/transfer_planning.json",
                       missing_telemetry=planning["missing"],
                       geometry_status=planning["status"])
    else:
        summary["planning"]="SKIPPED: contacts CSV not found"
    (out/"overview.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    return summary

if __name__=="__main__":
    main()
