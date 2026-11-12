"""Shared DSN operations and TT&C EPS/TCS accounting.

Scenario inputs are NOT verified DSN grants or flight hardware specifications.
Unknown component draws remain null; RF power radiated is not spacecraft heat.
"""
import json
from datetime import timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def policy_seconds(pass_type=None):
    p=json.loads((ROOT/"data"/"dsn_operational_policy.json").read_text(encoding="utf-8"))
    name=pass_type or p["default_pass_type"]
    key={"standard_ttc":"standard_ttc_setup_minutes",
         "ranging":"ranging_setup_minutes",
         "downlink_only":"downlink_setup_minutes",
         "uplink_downlink":"uplink_downlink_setup_minutes"}.get(name)
    if key is None:raise ValueError("Unknown DSN pass type")
    pre=(float(p[key])+float(p["acquisition_minutes"]))*60
    post=float(p["teardown_minutes"])*60
    return {"pass_type":name,"preparation_seconds":pre,"teardown_seconds":post,
            "source_status":p["status"]}

def usable_contacts(schedule,preparation_seconds,teardown_seconds):
    result=[]
    for c in schedule:
        a=c["start"]+timedelta(seconds=preparation_seconds)
        b=c["end"]-timedelta(seconds=teardown_seconds)
        if b>a:
            result.append({**c,"start":a,"end":b,"seconds":(b-a).total_seconds()})
    return result

def electrical_thermal(contacts,start,end,components,rf_power_w=None):
    """Contact-based electrical energy. Baseline is standby; TX replaces standby.

    components: standby_w, tx_dc_w, gimbal_tracking_w, memory_interface_w.
    Missing values produce null totals; no zero-filled complete budgets.
    """
    duration=(end-start).total_seconds()
    if duration<=0:raise ValueError("Invalid time horizon")
    tx_seconds=sum((c["end"]-c["start"]).total_seconds() for c in contacts)
    if tx_seconds>duration+1e-6:raise ValueError("Overlapping satellite contacts")
    names=("standby_w","tx_dc_w","gimbal_tracking_w","memory_interface_w")
    missing=[k for k in names if components.get(k) is None]
    if any(components.get(k) is not None and float(components[k])<0 for k in names):
        raise ValueError("Negative electrical load")
    standby=components.get("standby_w")
    tx=components.get("tx_dc_w")
    pointing=components.get("gimbal_tracking_w")
    memory=components.get("memory_interface_w")
    tx_mode=None if any(x is None for x in (standby,tx,pointing,memory)) else sum(float(x) for x in (standby,tx,pointing,memory))
    standby_mode=None if standby is None else float(standby)
    energy=None if tx_mode is None or standby_mode is None else (
        tx_mode*tx_seconds+standby_mode*(duration-tx_seconds))/3600
    if rf_power_w is not None and rf_power_w<0:raise ValueError("Invalid RF power")
    heat=None if tx_mode is None or rf_power_w is None else tx_mode-rf_power_w
    if heat is not None and heat<0:raise ValueError("RF output exceeds modeled electrical input")
    return {"status":"INCOMPLETE_HARDWARE_INPUTS" if missing or rf_power_w is None else "CALCULATED_FROM_SCENARIO_INPUTS",
            "missing_components":missing,"tx_seconds":tx_seconds,
            "standby_w":standby_mode,"tx_mode_w":tx_mode,
            "peak_mode_w":None if tx_mode is None or standby_mode is None else max(tx_mode,standby_mode),
            "energy_wh_horizon":energy,"average_w_horizon":None if energy is None else energy*3600/duration,
            "tx_heat_w":heat,"tx_heat_wh_horizon":None if heat is None else heat*tx_seconds/3600,
            "rf_radiated_w":rf_power_w,
            "scope":"TT&C incremental accounting only; Payload PNT excluded; spacecraft EPS/TCS totals not added"}
