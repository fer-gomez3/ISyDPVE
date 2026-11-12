"""Robust Excel export using openpyxl."""
import json
import csv
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill

def export(output="outputs/SELENA_TTC_Model.xlsx",root="."):
    root=Path(root)
    wb=Workbook()
    ws=wb.active
    ws.title="Data Budget"
    ws.append(["Subsystem","Rate bps","Mbit/day","MB/day","Origin","Confirm"])
    source=root/"outputs/telemetry_generation.json"
    if source.exists():
        data=json.loads(source.read_text(encoding="utf-8"))
        for s in data["subsystems"]:
            ws.append([s["subsystem"],s["rate_bps"],s["mbit_per_day"],s["mb_per_day"],s["source_type"],s["requires_confirmation"]])
    else:
        ws.append(["Telemetry file not generated; run main.py first"])
    for filename,title in [
        ("dsn_allocated_windows.csv","DSN Windows"),
        ("transfer_by_subsystem.csv","Transfer by Subsystem"),
        ("downlink_contacts.csv","Downlink Contacts"),
        ("telemetry_generation.csv","Telemetry CSV")]:
        p=root/"outputs"/filename
        if p.exists():
            sheet=wb.create_sheet(title)
            with p.open(encoding="utf-8",newline="") as f:
                for row in csv.reader(f):
                    sheet.append(row)
    for filename,title in [
        ("link_budget.json","Link Budget"),
        ("hga_sizing.json","HGA Sizing"),
        ("power_budget.json","Power Budget"),
        ("dsn_allocation_summary.json","DSN Allocation"),
        ("downlink_simulation.json","Downlink Simulation")]:
        p=root/"outputs"/filename
        if p.exists():
            sheet=wb.create_sheet(title)
            sheet.append(["Parameter","Value"])
            data=json.loads(p.read_text(encoding="utf-8"))
            for key,value in data.items():
                sheet.append([key,json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else value])
    assumptions=wb.create_sheet("Limitations")
    for row in [
        ["Issue","Status"],
        ["Orbit geometry","Historical windows shifted to 2030; NOT physical propagation"],
        ["DSN","Hypothetical allocation; NOT booked"],
        ["Telemetry","PDF or explicitly PRELIMINARY assumptions"],
        ["HGA","0.38 m assumed, not selected hardware"],
        ["Mass","11.40 kg TT&C/OBDH allocation, not itemized verified mass"]]:
        assumptions.append(row)
    for sheet in wb.worksheets:
        sheet.freeze_panes="A2"
        sheet.auto_filter.ref=sheet.dimensions
        for cell in sheet[1]:
            cell.fill=PatternFill("solid",fgColor="17365D")
            cell.font=Font(bold=True,color="FFFFFF")
        for col in sheet.columns:
            sheet.column_dimensions[col[0].column_letter].width=25
    target=root/output
    target.parent.mkdir(parents=True,exist_ok=True)
    wb.save(target)
    return target

if __name__=="__main__":
    print(export())
