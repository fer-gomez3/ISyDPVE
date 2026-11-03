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
from ttc.xband_trade_study import from_file as evaluate_xband_trade
from ttc.contact_energy_optimizer import compute as rank_contacts
from ttc.downlink_simulation import compute as simulate_downlink
from ttc.dsn_allocation import compute_allocation

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
    trade=evaluate_xband_trade()
    (out/"xband_trade_study.json").write_text(json.dumps(trade,indent=2)+"\n",encoding="utf-8")
    allocation=compute_allocation(args.contacts,output_dir=args.output_dir) if Path(args.contacts).exists() else None
    energy_ranking=rank_contacts(windows_path=str(out/'dsn_allocated_windows.csv'),output_path=str(out/'contact_energy_ranking.json')) if allocation else None
    simulation=simulate_downlink(contacts_path=args.contacts,output_dir=args.output_dir) if allocation else None
    summary={"dsn_allocation":"outputs/dsn_allocation_summary.json" if allocation else "SKIPPED",
             "downlink_simulation":"outputs/downlink_simulation.json" if simulation else "SKIPPED",
             "contact_energy_ranking":str(out/"contact_energy_ranking.json") if energy_ranking else "SKIPPED","contact_energy_status":energy_ranking["status"] if energy_ranking else "SKIPPED","xband_trade_study":str(out/"xband_trade_study.json"),"xband_trade_status":trade["status"],"link_budget":"outputs/link_budget.json","link_status":rf_link["status"],"engineering":"outputs/subsystem_interfaces.json",
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
