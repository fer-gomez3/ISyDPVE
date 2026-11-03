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
from ttc.export_excel import export as export_excel
from ttc.shift_contact_epoch import shift_contacts
from ttc.dsn_access_sensitivity import compute as dsn_sensitivity
from ttc.downlink_simulation import compute as simulate_downlink
from ttc.dsn_allocation import compute_allocation
from ttc.hga_sizing import from_files as evaluate_hga
from ttc.telemetry_generation import compute as compute_telemetry

def main():
    parser=argparse.ArgumentParser(description="SELENA TT&C / OBDH engineering overview")
    parser.add_argument("--requirements",default="data/transfer_requirements.json")
    parser.add_argument("--contacts",default="data/contacts_master.csv")
    parser.add_argument("--scenario-2030",action="store_true",default=True,help="Shift contact dates to 2030 scenario epoch")
    parser.add_argument("--epoch",default="2030-07-14T22:10:10.811Z")
    parser.add_argument("--link-input",default="data/link_budget_inputs.json")
    parser.add_argument("--output-dir",default="outputs")
    args=parser.parse_args()
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    contacts_path=args.contacts
    if args.scenario_2030 and Path(contacts_path).exists():
        shifted=out/"contacts_2030_scenario.csv"
        shift_contacts(contacts_path,shifted,args.epoch)
        contacts_path=str(shifted)
    requirements=load_requirements(args.requirements)
    link=json.loads(Path(args.link_input).read_text(encoding="utf-8"))
    # Keep the original engineering reference and the editable planning model distinct.
    telemetry=compute_telemetry(output_dir=args.output_dir)
    generated_cfg=json.loads(Path("data/telemetry_detailed_scenario.json").read_text(encoding="utf-8"))
    calculated={r["subsystem"]:r for r in telemetry["subsystems"]}
    for stream in generated_cfg["streams"]:
        if stream["name"] in calculated:
            row=calculated[stream["name"]]
            stream["rate_bps"]=row["rate_bps"]
            stream["status"]="PDF" if row["source_type"]=="PDF" else "PRE"
    generated_telemetry_path=out/"telemetry_detailed_generated.json"
    generated_telemetry_path.write_text(json.dumps(generated_cfg,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    engineering=calculate()
    (out/"subsystem_interfaces.json").write_text(json.dumps(engineering,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    power=evaluate(link)
    (out/"power_budget.json").write_text(json.dumps(power,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    rf_link=evaluate_link(args.link_input)
    (out/"link_budget.json").write_text(json.dumps(rf_link,indent=2)+"\n",encoding="utf-8")
    hga=evaluate_hga(link_path=args.link_input)
    (out/"hga_sizing.json").write_text(json.dumps(hga,indent=2)+"\n",encoding="utf-8")
    trade=evaluate_xband_trade()
    (out/"xband_trade_study.json").write_text(json.dumps(trade,indent=2)+"\n",encoding="utf-8")
    allocation=compute_allocation(contacts_path,output_dir=args.output_dir) if Path(contacts_path).exists() else None
    access_sensitivity=dsn_sensitivity(contacts_path,telemetry_path=str(generated_telemetry_path),output_dir=args.output_dir) if allocation else None
    energy_ranking=rank_contacts(windows_path=str(out/'dsn_allocated_windows.csv'),output_path=str(out/'contact_energy_ranking.json')) if allocation else None
    simulation=simulate_downlink(telemetry_path=str(generated_telemetry_path),contacts_path=contacts_path,output_dir=args.output_dir) if allocation else None
    summary={"telemetry_generation":str(out/"telemetry_generation.json"),"telemetry_total_bps":telemetry["total_rate_bps_per_spacecraft"],"hga_sizing":str(out/"hga_sizing.json"),"hga_status":hga["status"],"dsn_access_sensitivity":str(out/"dsn_access_sensitivity.json") if access_sensitivity else "SKIPPED","dsn_allocation":str(out/"dsn_allocation_summary.json") if allocation else "SKIPPED",
             "downlink_simulation":str(out/"downlink_simulation.json") if simulation else "SKIPPED",
             "contact_energy_ranking":str(out/"contact_energy_ranking.json") if energy_ranking else "SKIPPED","contact_energy_status":energy_ranking["status"] if energy_ranking else "SKIPPED","xband_trade_study":str(out/"xband_trade_study.json"),"xband_trade_status":trade["status"],"link_budget":"outputs/link_budget.json","link_status":rf_link["status"],"engineering":"outputs/subsystem_interfaces.json",
             "power":"outputs/power_budget.json",
             "power_status":power["status"],"power_missing_inputs":power["missing_inputs"]}
    if Path(contacts_path).exists():
        planning=compute(requirements,contacts_path=contacts_path,output_dir=args.output_dir)
        summary.update(planning="outputs/transfer_planning.json",
                       missing_telemetry=planning["missing"],
                       geometry_status=planning["status"])
    else:
        summary["planning"]="SKIPPED: contacts CSV not found"
    (out/"overview.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    workbook=export_excel(output=str(out/"SELENA_TTC_Model.xlsx"))
    summary["excel_workbook"]=str(workbook)
    (out/"overview.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    return summary

if __name__=="__main__":
    main()
