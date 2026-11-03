"""Generate color-coded SELENA engineering workbook from the repository inputs.

Requires artifact_tool. Run after main.py:
python -m ttc.export_excel
"""
import csv
import json
from pathlib import Path
from artifact_tool import Workbook, SpreadsheetFile

def export(output="outputs/SELENA_TTC_Model.xlsx",root="."):
    root=Path(root)
    cfg=json.loads((root/"data/telemetry_detailed_scenario.json").read_text(encoding="utf-8"))
    policy=json.loads((root/"data/dsn_allocation_scenario.json").read_text(encoding="utf-8"))
    wb=Workbook.create()
    def sheet(name,headers,rows):
        ws=wb.worksheets.add(name)
        data=[headers]+[[v if v is not None else "" for v in row] for row in rows]
        ws.get_range_by_indexes(0,0,len(data),len(headers)).values=data
        ws.get_range_by_indexes(0,0,1,len(headers)).format.fill="#17365D"
        ws.get_range_by_indexes(0,0,1,len(headers)).format.font.color="#FFFFFF"
        ws.get_range_by_indexes(0,0,len(data),len(headers)).format.column_width=19
        ws.freeze_panes.freeze_rows(1)
        return ws
    streams=cfg["streams"]
    rows=[[s["name"],s["rate_bps"],s["priority"],s["max_age_hours"],s["status"],s["rate_bps"]*86400/8e6] for s in streams]
    ws=sheet("Data Budget",["Stream","Rate bps","Priority","Max age h","Origin","MB per day"],rows)
    for i,s in enumerate(streams,2):
        ws.get_range("E"+str(i)).format.fill="#C6EFCE" if s["status"]=="PDF" else "#FCE4D6"
        ws.get_range("F"+str(i)).formulas=[["=B"+str(i)+"*86400/8000000"]]
    ws.get_range("A"+str(len(rows)+3)+":B"+str(len(rows)+6)).values=[
        ["LEGEND",""],["Green","PDF confirmed"],["Orange","Preliminary / confirm"],["Blue","Calculated"]]
    ws.get_range("A"+str(len(rows)+4)).format.fill="#C6EFCE"
    ws.get_range("A"+str(len(rows)+5)).format.fill="#FCE4D6"
    ws.get_range("A"+str(len(rows)+6)).format.fill="#DDEBF7"
    ws.get_range("F2:F"+str(len(rows)+1)).format.fill="#DDEBF7"
    contacts_path=root/"outputs/dsn_allocated_windows.csv"
    if contacts_path.exists():
        with contacts_path.open(encoding="utf-8",newline="") as f:contacts=list(csv.DictReader(f))
        cols=["satellite","station","candidate_start_utc","candidate_end_utc","geometric_candidate_seconds","allocation_fraction","assigned_seconds","useful_tx_seconds"]
        sheet("DSN Windows",cols,[[float(c[k]) if k in ("geometric_candidate_seconds","allocation_fraction","assigned_seconds","useful_tx_seconds") else c[k] for k in cols] for c in contacts])
    sim_path=root/"outputs/downlink_simulation.json"
    if sim_path.exists():
        sim=json.loads(sim_path.read_text(encoding="utf-8"))
        satrows=[[k,v["generated_mbit"],v["downloaded_mbit"],v["remaining_mbit"],v["peak_backlog_mbit"],", ".join(v["deadline_risk_streams"])] for k,v in sim.get("satellites",{}).items()]
        sheet("X-band Results",["Satellite","Generated Mbit","Downloaded Mbit","Remaining Mbit","Peak buffer Mbit","Deadline risks"],satrows)
    link_path=root/"outputs/link_budget.json"
    if link_path.exists():
        link=json.loads(link_path.read_text(encoding="utf-8"))
        sheet("Link Budget",["Parameter","Value"],[[k,str(v) if isinstance(v,(dict,list)) else v] for k,v in link.items()])
    sheet("Assumptions",["Parameter","Value","Status"],[
        ["Allocation default",policy["default_fraction"],"PRE"],
        ["Setup minutes",policy["setup_minutes"],"PRE"],
        ["Protocol overhead",cfg["policy"]["protocol_overhead_fraction"],"PRE"],
        ["X-band gross bps",cfg["policy"]["net_downlink_bps"],"PRE"],
        ["Geometry","Historical 2020, not mission 2030","NOT VALIDATED"],
        ["DSN booking","None confirmed","NOT VALIDATED"],
        ["Telemetry components","Aggregated rates; PDF totals override individual estimates","PRE"]])
    dest=root/output;dest.parent.mkdir(parents=True,exist_ok=True)
    SpreadsheetFile.export_xlsx(wb).save(str(dest))
    return dest

if __name__=="__main__":
    print(export())
