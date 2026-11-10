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
from ttc.export_workbook import export as export_excel
from ttc.shift_contact_epoch import shift_contacts
from ttc.dsn_access_sensitivity import compute as dsn_sensitivity
from ttc.downlink_simulation import compute as simulate_downlink
from ttc.dsn_allocation import compute_allocation
from ttc.hga_sizing import from_files as evaluate_hga
from ttc.telemetry_generation import compute as compute_telemetry, apply_computed_rates
from ttc.transfer_planning import stream_requirements
from ttc import data_interface
from ttc.parameters import apply_policy, hga_link_defaults
from ttc.satellite_outputs import write as write_satellite_outputs

def main():
    parser=argparse.ArgumentParser(description="SELENA TT&C / OBDH engineering overview")
    parser.add_argument("--requirements",default="data/transfer_requirements.json")
    parser.add_argument("--contacts",default="data/contacts_master.csv")
    parser.add_argument("--no-epoch-shift",action="store_true",help="Use the contacts file as supplied (e.g. real propagated 2030 windows). By default the historical 2020 windows are shifted to the 2030 epoch as a HYPOTHETICAL scenario.")
    parser.add_argument("--epoch",default="2030-07-14T22:10:10.811Z")
    parser.add_argument("--telemetry-input",default="data/telemetry_generation_inputs.json",help="Sensor/channel inventories (what-if runs without editing the repository data)")
    parser.add_argument("--link-input",default="data/link_budget_inputs.json")
    parser.add_argument("--output-dir",default="outputs")
    parser.add_argument("--integrated",action="store_true",help="Run detailed DSN backlog and antenna/EPS/TCS interface outputs")
    parser.add_argument("--rf-power-w",type=float,default=None,help="Available RF power budget in W; omitted means antenna diameter TBD")
    args=parser.parse_args()
    out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
    contacts_path=args.contacts
    shifted_scenario=not args.no_epoch_shift
    if shifted_scenario and Path(contacts_path).exists():
        shifted=out/"contacts_2030_scenario.csv"
        shift_contacts(contacts_path,shifted,args.epoch)
        contacts_path=str(shifted)
    link=json.loads(Path(args.link_input).read_text(encoding="utf-8"))
    # Keep the original engineering reference and the editable planning model distinct.
    telemetry=compute_telemetry(input_path=args.telemetry_input,output_dir=args.output_dir)
    generated_cfg=json.loads(Path("data/telemetry_detailed_scenario.json").read_text(encoding="utf-8"))
    generated_cfg["policy"]=apply_policy(generated_cfg["policy"])
    apply_computed_rates(generated_cfg,telemetry["subsystems"],set_status=True)
    generated_telemetry_path=out/"telemetry_detailed_generated.json"
    generated_telemetry_path.write_text(json.dumps(generated_cfg,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    generated_requirements=json.loads(Path(args.requirements).read_text(encoding="utf-8"))
    generated_requirements["policy"]=apply_policy(generated_requirements["policy"])
    apply_computed_rates(generated_requirements,telemetry["subsystems"])
    generated_requirements_path=out/"transfer_requirements_generated.json"
    generated_requirements_path.write_text(json.dumps(generated_requirements,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    requirements=load_requirements(str(generated_requirements_path))
    interface=data_interface.write(telemetry,stream_requirements(requirements),args.output_dir,{s["name"]:s["mode"] for s in requirements["streams"]})
    engineering=calculate()
    (out/"subsystem_interfaces.json").write_text(json.dumps(engineering,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    hga=evaluate_hga(link_path=args.link_input)
    # Wire the HGA design into the link budget: gain, frequency and rate come from the HGA
    # definition when link_budget_inputs.json leaves them unset (no new values are introduced).
    defaults=hga_link_defaults()
    link={**link,**{k:(link.get(k) if link.get(k) is not None else v) for k,v in defaults.items()}}
    power=evaluate(link)
    (out/"power_budget.json").write_text(json.dumps(power,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    from ttc.link_budget import evaluate_link as evaluate_link_dict
    rf_link=evaluate_link_dict(link)
    (out/"link_budget.json").write_text(json.dumps(rf_link,indent=2)+"\n",encoding="utf-8")
    (out/"hga_sizing.json").write_text(json.dumps(hga,indent=2)+"\n",encoding="utf-8")
    trade=evaluate_xband_trade(extra_gains_dbi=[defaults["tx_gain_dbi"]])
    (out/"xband_trade_study.json").write_text(json.dumps(trade,indent=2)+"\n",encoding="utf-8")
    allocation=compute_allocation(contacts_path,output_dir=args.output_dir) if Path(contacts_path).exists() else None
    access_sensitivity=dsn_sensitivity(contacts_path,telemetry_path=str(generated_telemetry_path),output_dir=args.output_dir) if allocation else None
    energy_ranking=rank_contacts(windows_path=str(out/'dsn_allocated_windows.csv'),output_path=str(out/'contact_energy_ranking.json')) if allocation else None
    simulation=simulate_downlink(telemetry_path=str(generated_telemetry_path),contacts_path=contacts_path,output_dir=args.output_dir) if allocation else None
    per_satellite=write_satellite_outputs(args.output_dir) if simulation else None
    summary={"geometry_source":"SHIFTED_2020_HISTORICAL_SCENARIO_NOT_PROPAGATION" if shifted_scenario else "CONTACTS_AS_SUPPLIED","telemetry_generation":str(out/"telemetry_generation.json"),"telemetry_total_bps":telemetry["total_rate_bps_per_spacecraft"],"data_generation_interface":str(out/"data_generation_interface.csv"),"subsystem_engineering":str(out/"subsystem_engineering.json"),"hga_sizing":str(out/"hga_sizing.json"),"hga_status":hga["status"],"dsn_access_sensitivity":str(out/"dsn_access_sensitivity.json") if access_sensitivity else "SKIPPED","dsn_allocation":str(out/"dsn_allocation_summary.json") if allocation else "SKIPPED",
             "downlink_simulation":str(out/"downlink_simulation.json") if simulation else "SKIPPED",
             "per_satellite":str(out/"per_satellite") if per_satellite else "SKIPPED",
             "contact_energy_ranking":str(out/"contact_energy_ranking.json") if energy_ranking else "SKIPPED","contact_energy_status":energy_ranking["status"] if energy_ranking else "SKIPPED","xband_trade_study":str(out/"xband_trade_study.json"),"xband_trade_status":trade["status"],"link_budget":str(out/"link_budget.json"),"link_status":rf_link["status"],"engineering":str(out/"subsystem_interfaces.json"),
             "power":str(out/"power_budget.json"),
             "power_status":power["status"],"power_missing_inputs":power["missing_inputs"]}
    if Path(contacts_path).exists():
        planning=compute(requirements,contacts_path=contacts_path,output_dir=args.output_dir)
        summary.update(planning=str(out/"transfer_planning.json"),
                       missing_telemetry=planning["missing"],
                       geometry_status=planning["status"])
    else:
        summary["planning"]="SKIPPED: contacts CSV not found"
    (out/"overview.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    workbook=export_excel(output=str(out/"SELENA_TTC_Model.xlsx"),link_input=args.link_input,out_dir=args.output_dir)
    summary["excel_workbook"]=str(workbook)
    (out/"overview.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    if args.integrated:
        from ttc.dsn_pipeline import run as run_dsn_pipeline
        from ttc.integrated_requirements import build as build_integrated
        detailed=out/"integrated"
        run_dsn_pipeline(contacts_path=contacts_path,output_dir=str(detailed),
                         telemetry_profile="scenario",make_plots=False)
        # Reuse generated telemetry and the detailed candidate-window backlog.
        (detailed/"telemetry_generation.json").write_text(
            (out/"telemetry_generation.json").read_text(encoding="utf-8"),encoding="utf-8")
        integrated=build(detailed,rf_power_w=args.rf_power_w)
        summary["integrated_requirements"]=integrated
        (out/"overview.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    return summary

if __name__=="__main__":
    main()
