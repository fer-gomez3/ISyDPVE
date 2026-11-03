"""Editable subsystem requirements -> contact demands -> EPS/TCS interfaces.

Priority sets a planning deadline, NOT a magically derived physical transfer rate.
No claimed DSN allocation or RF power without independent transmitter inputs.
"""
import csv
import json
import math
from datetime import timedelta
from pathlib import Path
from .contact_analysis import load_contacts, candidate_schedule, dt
from .parameters import apply_policy

def load_requirements(path="data/transfer_requirements.json"):
    with open(path,encoding="utf-8") as f: cfg=json.load(f)
    cfg["policy"]=apply_policy(cfg["policy"])
    return cfg

def stream_rate(s):
    mode=s["mode"]
    if mode=="continuous":
        v=s.get("rate_bps")
        return None if v is None else float(v)
    if mode=="event":
        size=s.get("bytes_per_event"); period=s.get("event_interval_hours")
        if size is not None and period is not None:
            if float(period)<=0: raise ValueError("event_interval_hours must be positive")
            return float(size)*8/(float(period)*3600)
        v=s.get("rate_bps")
        return None if v is None else float(v)  # Explicit preliminary average for event stream
    raise ValueError("Unsupported mode: "+str(mode))

def recurrence_display(hours):
    """Human-readable recurrence; scheduling still uses the exact hourly deadline."""
    if hours <= 24:
        period, unit = 24.0, "day"
    elif hours <= 168:
        period, unit = 168.0, "week"
    elif hours <= 720:
        period, unit = 720.0, "30_day_month"
    else:
        period, unit = 8760.0, "365_day_year"
    return period / hours, unit

def stream_requirements(cfg):
    p=cfg["policy"]; out=[]
    for s in cfg["streams"]:
        priority=int(s["priority"])
        if priority not in range(1,6):raise ValueError("Priority must be 1..5")
        age=s.get("max_age_hours")
        if age is None:age=p["priority_max_age_hours"][str(priority)]
        age=float(age)
        if age<=0:raise ValueError("max_age_hours must be positive")
        rate=stream_rate(s)
        if rate is not None and (rate<0 or not math.isfinite(rate)):raise ValueError("Invalid rate")
        frequency, frequency_unit = recurrence_display(age)
        out.append(dict(name=s["name"],priority=priority,deadline_hours=age,
            mean_rate_bps=rate,generated_mbit_per_day=None if rate is None else rate*86400/1e6,
            required_transfers_per_period=frequency,recurrence_period=frequency_unit,source=s.get("source")))
    return out

def compute(cfg,contacts_path="data/contacts_master.csv",output_dir="outputs"):
    p=cfg["policy"]; overhead=float(p["protocol_overhead_fraction"])
    if not 0<=overhead<1:raise ValueError("Invalid overhead")
    min_s=float(p["min_contact_minutes"])*60
    setup_s=float(p["setup_minutes"])*60
    if min_s<0 or setup_s<0:raise ValueError("Invalid contact policy")
    net=p.get("net_downlink_bps")
    if net is not None and (float(net)<=0 or not math.isfinite(float(net))):raise ValueError("Invalid net rate")
    streams=stream_requirements(cfg)
    contacts=load_contacts(contacts_path)
    candidate=candidate_schedule(contacts)
    start=min(c["start"] for c in contacts);end=max(c["end"] for c in contacts)
    epoch_s=(end-start).total_seconds()
    rows=[];contacts_out=[]
    for sat in sorted({c["satellite"] for c in contacts}):
        windows=sorted((x for x in candidate if x["satellite"]==sat and x["seconds"]>=min_s),
                       key=lambda x:x["start"])
        for w in windows:
            usable=max(0,w["seconds"]-setup_s)
            contacts_out.append(dict(satellite=sat,station=w["station"],start_utc=w["start"].isoformat(),
                end_utc=w["end"].isoformat(),usable_seconds=usable,
                scenario_capacity_mbit=None if net is None else usable*float(net)*(1-overhead)/1e6))
        for stream in streams:
            rate=stream["mean_rate_bps"]
            generated=None if rate is None else rate*epoch_s
            usable_total=sum(max(0,w["seconds"]-setup_s) for w in windows)
            tx_s=None if generated is None or net is None else generated/(float(net)*(1-overhead))
            deadline=timedelta(hours=stream["deadline_hours"])
            # Check worst geometric opportunity gap; no DSN booking guarantee.
            last=start;gap=0.
            for w in windows:
                gap=max(gap,(w["start"]-last).total_seconds())
                last=max(last,w["end"])
            gap=max(gap,(end-last).total_seconds())
            rows.append(dict(satellite=sat,subsystem=stream["name"],priority=stream["priority"],
                max_data_age_hours=stream["deadline_hours"],required_transfers_per_period=stream["required_transfers_per_period"],recurrence_period=stream["recurrence_period"],
                generation_bps=rate,generated_mbit_epoch=None if generated is None else generated/1e6,
                ideal_required_tx_hours_epoch=None if tx_s is None else tx_s/3600,
                candidate_usable_hours_epoch=usable_total/3600,
                gap_hours_candidate=gap/3600,
                deadline_passes_candidate_geometry=gap<=deadline.total_seconds(),
                capacity_sufficient_candidate=None if tx_s is None else tx_s<=usable_total,
                # Station attribution requires a stream-aware scheduling optimizer.
                assigned_station=None,assigned_tx_hours=None))
    dc=p.get("transmitter_dc_w");rf=p.get("transmitter_rf_w");idle=p.get("transmitter_standby_w")
    if dc is not None and float(dc)<0:raise ValueError("Invalid DC power")
    if rf is not None and float(rf)<0:raise ValueError("Invalid RF power")
    if dc is not None and rf is not None and float(rf)>float(dc):raise ValueError("RF cannot exceed DC")
    known=sum(s["mean_rate_bps"] for s in streams if s["mean_rate_bps"] is not None)
    complete=all(s["mean_rate_bps"] is not None for s in streams)
    sat_tx_s=None if net is None or not complete else known*epoch_s/(float(net)*(1-overhead))
    energy_wh=None if dc is None or sat_tx_s is None else float(dc)*sat_tx_s/3600
    heat_w=None if dc is None or rf is None else float(dc)-float(rf)
    result=dict(status="SCENARIO_NOT_VALIDATED",geometry_epoch=[start.isoformat(),end.isoformat()],
        note="Historical 2020 candidate geometry; not booked DSN time. No simultaneous station allocations beyond candidate heuristic.",
        priority_rule=p["priority_max_age_hours"],streams=streams,telemetry_complete=complete,
        known_total_bps=known,missing=[s["name"] for s in streams if s["mean_rate_bps"] is None],
        power_interfaces=dict(eps_tx_dc_w=dc,eps_tx_standby_w=idle,
            eps_tx_energy_wh_per_satellite_epoch=energy_wh,
            thermal_tx_heat_w_during_tx=heat_w,
            rf_tx_w=rf,assumption="Input hardware power, not inferred from traffic"),
        scheduling_warning="Per-station subsystem time not allocated until rates and DSN allocation known",
        per_satellite_subsystem=rows,contacts=contacts_out)
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"transfer_planning.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    with (out/"transfer_by_subsystem.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with (out/"transfer_contact_capacity.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(contacts_out[0]));w.writeheader();w.writerows(contacts_out)
    return result

if __name__=="__main__":
    r=compute(load_requirements())
    print(json.dumps({"known_total_bps":r["known_total_bps"],"missing":r["missing"],
        "power_interfaces":r["power_interfaces"],"output":"outputs/transfer_planning.json"},indent=2))
