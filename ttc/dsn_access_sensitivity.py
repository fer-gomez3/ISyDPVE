"""Hypothetical network-wide DSN access sensitivity, not confirmed station bookings."""
import json
from pathlib import Path
from .contact_analysis import load_contacts
from .dsn_allocation import allocate
from .parameters import apply_policy, load as load_parameters

def compute(contacts_path,policy_path="data/dsn_allocation_scenario.json",telemetry_path="data/telemetry_detailed_scenario.json",output_dir="outputs"):
    params=load_parameters()
    policy=apply_policy(json.loads(Path(policy_path).read_text(encoding="utf-8")),params)
    cfg=json.loads(Path(telemetry_path).read_text(encoding="utf-8"))
    cfg["policy"]=apply_policy(cfg.get("policy",{}),params)
    contacts=load_contacts(contacts_path)
    sats=sorted({c["satellite"] for c in contacts})
    rate=sum(float(s["rate_bps"]) for s in cfg["streams"])
    effective=float(cfg["policy"]["net_downlink_bps"])*(1-float(cfg["policy"]["protocol_overhead_fraction"]))
    generated_mb_per_sat_day=rate*86400/8e6
    ideal_tx_min_per_sat=rate*86400/effective/60
    rows=[]
    for hours in policy.get("daily_network_hours_sensitivity",[1,3,6]):
        for setup in policy.get("setup_minutes_sensitivity",[5,15,30]):
            p={**policy,"daily_network_hours":hours,"setup_minutes":setup,"min_contact_minutes":setup+float(params["min_useful_tx_minutes"])}
            windows=allocate(contacts,p)
            assigned=sum(w["assigned_seconds"] for w in windows)/3600
            useful=sum(w["useful_tx_seconds"] for w in windows)/3600
            rows.append(dict(network_hours_per_day=hours,setup_minutes=setup,
                assigned_hours_in_input_epoch=assigned,useful_hours_in_input_epoch=useful,
                nominal_data_capacity_mb_in_epoch=useful*3600*effective/8e6,
                nominal_generated_mb_per_sat_day=generated_mb_per_sat_day,
                ideal_tx_minutes_per_sat_day=ideal_tx_min_per_sat,
                satellites=len(sats),scenario_only=True))
    result={"status":"HYPOTHETICAL_NOT_BOOKED","note":"Capacity is an upper bound. Access cap is shared fairly among satellites per UTC day; windows crossing midnight are not split; minimum contact = setup + minimum useful transmit time. No packet-level scheduling, actual DSN allocations, or validated 2030 geometry.","cases":rows}
    dest=Path(output_dir)/"dsn_access_sensitivity.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result
