"""Adaptive SELENA store-and-forward planning (preliminary, not a DSN booking).

Run from repository root: python -m ttc.adaptive_storage
Only geometric windows are used; historical 2020 dates are relabeled to 2030.
All memory capacities, environmental events and DSN availability are scenario inputs.
"""
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from .contact_analysis import load_contacts
from .telemetry_generation import calculate, apply_computed_rates
from .transfer_planning import stream_requirements
from .priority_memory_policy import ordered_streams, choose_due_tier, volume_shares

ROOT = Path(__file__).resolve().parents[1]
STEP = 300  # seconds; planning discretization

def iso(t):
    return t.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def shift_contacts(contacts, target):
    """Calendar-only translation: NOT a 2030 propagation."""
    base = min(c["start"] for c in contacts)
    delta = target - base
    return [{**c, "start": c["start"] + delta, "end": c["end"] + delta} for c in contacts]

def events_at(t, events, sat):
    active = []
    for e in events:
        if e["start"] <= t < e["end"] and (not e["satellites"] or sat in e["satellites"]):
            active.append(e)
    return active

def plan(config_path=None, output_dir=None):
    path = Path(config_path or ROOT / "data" / "adaptive_storage_scenario.json")
    cfg = json.loads(path.read_text(encoding="utf-8"))
    shared = json.loads((ROOT / "data" / "ttc_parameters.json").read_text(encoding="utf-8"))
    tel = json.loads((ROOT / "data" / "telemetry_detailed_scenario.json").read_text(encoding="utf-8"))
    inputs = json.loads((ROOT / "data" / "telemetry_generation_inputs.json").read_text(encoding="utf-8"))
    apply_computed_rates(tel, calculate(inputs)["subsystems"])
    streams = stream_requirements(tel)
    if any(s["mean_rate_bps"] is None for s in streams):
        raise ValueError("Unknown telemetry generation rate")
    target = datetime.fromisoformat(cfg["scenario_start_utc"].replace("Z", "+00:00"))
    contacts = shift_contacts(load_contacts(ROOT / "data" / "contacts_master.csv"), target)
    sats = sorted({c["satellite"] for c in contacts})
    stations = sorted({c["station"] for c in contacts})
    end = min(max(c["end"] for c in contacts), target + timedelta(hours=float(cfg["horizon_hours"])))
    if end <= target: raise ValueError("Empty simulation horizon")
    capacity = float(cfg["memory_capacity_mbit_per_satellite"]) * 1e6
    if capacity <= 0: raise ValueError("Memory capacity must be positive")
    reserve = float(cfg["memory_reserve_fraction"])
    if not 0 <= reserve < 1: raise ValueError("Invalid reserve")
    effective = float(shared["downlink_gross_bps"]) * (1 - float(shared["protocol_overhead_fraction"]))
    policy = json.loads((ROOT / "data" / "dsn_operational_policy.json").read_text(encoding="utf-8"))
    pass_type = cfg.get("dsn_pass_type", policy["default_pass_type"])
    if pass_type not in ("standard_ttc", "ranging", "downlink_only", "uplink_downlink"):
        raise ValueError("Unsupported DSN pass type")
    setup_minutes = (policy["standard_ttc_setup_minutes"] if pass_type == "standard_ttc" else
                     policy["ranging_setup_minutes"] if pass_type == "ranging" else
                     policy["downlink_setup_minutes"] if pass_type == "downlink_only" else
                     policy["uplink_downlink_setup_minutes"])
    setup_steps = math.ceil(float(setup_minutes) * 60 / STEP)
    acquisition_steps = math.ceil(float(policy["acquisition_minutes"]) * 60 / STEP)
    teardown_steps = math.ceil(float(policy["teardown_minutes"]) * 60 / STEP)
    overhead_steps = setup_steps + acquisition_steps + teardown_steps
    min_steps = math.ceil(float(shared["min_useful_tx_minutes"]) * 60 / STEP)
    if setup_steps < 0 or min_steps < 1: raise ValueError("Invalid contact policy")
    cap_per_day = float(shared["dsn_daily_network_hours"]) * 3600
    max_gap = float(cfg["max_hours_between_downlinks"]) * 3600
    if max_gap <= 0: raise ValueError("Invalid recurrence")
    thresholds = cfg["warning_thresholds"]
    if sorted(thresholds) != thresholds or any(not 0 < x < 1 for x in thresholds):
        raise ValueError("Invalid warning thresholds")
    evs = []
    for e in cfg["space_environment_events"]:
        a = datetime.fromisoformat(e["start_utc"].replace("Z", "+00:00"))
        b = datetime.fromisoformat(e["end_utc"].replace("Z", "+00:00"))
        if b <= a or float(e["rate_multiplier"]) < 1: raise ValueError("Invalid event")
        evs.append({**e, "start": a, "end": b, "satellites": set(e.get("satellites", []))})
    unavailable = {}
    for station, intervals in cfg.get("ground_station_unavailable_utc", {}).items():
        unavailable[station] = [(datetime.fromisoformat(a.replace("Z","+00:00")),
                                 datetime.fromisoformat(b.replace("Z","+00:00"))) for a,b in intervals]
    allowed = cfg.get("ground_station_enabled", {})
    initial = float(cfg.get("initial_memory_fraction", 0))
    if not 0 <= initial < 1: raise ValueError("Invalid initial fill")
    # Time-stamped FIFO chunks: [generation_time, bits] for exact age checks.
    fifo = {sat: {stream["name"]: [] for stream in streams} for sat in sats}
    dropped = defaultdict(float)
    backlog = {sat: {s["name"]: capacity * initial / len(streams) for s in streams} for sat in sats}
    if initial:
        for sat in sats:
            for stream in streams:
                fifo[sat][stream["name"]].append([target,capacity*initial/len(streams)])
    last_downlink = {sat: target for sat in sats}
    produced = defaultdict(float); sent = defaultdict(float)
    initial_bits = capacity*initial/len(streams)
    peak = defaultdict(float); violations = defaultdict(set)
    history = []; schedule = []; daily_used = defaultdict(float)
    active_links = {}  # sat -> contact state
    last_served_tier = {sat: {p: target for p in range(1,6)} for sat in sats}
    last_sample = {}
    t = target
    while t < end:
        dt = min(STEP, (end-t).total_seconds())
        # Generate data, including configurable environmental burst multipliers.
        for sat in sats:
            active_events = events_at(t, evs, sat)
            for s in streams:
                multiplier = max([float(e["rate_multiplier"]) for e in active_events
                                  if not e.get("subsystems") or s["name"] in e["subsystems"]] or [1.])
                bits = s["mean_rate_bps"] * dt * multiplier
                backlog[sat][s["name"]] += bits
                fifo[sat][s["name"]].append([t, bits])
                produced[(sat,s["name"])] += bits
        # Keep links completing during this tick reserved until the tick ends.
        just_finished_stations=set()
        just_finished_satellites=set()
        # Advance ongoing contacts. Station and satellite resources stay locked.
        for sat, link in list(active_links.items()):
            link["remaining"] -= 1
            if link["setup"] > 0:
                link["setup"] -= 1
            elif link["remaining"] <= teardown_steps:
                pass  # teardown: no telemetry transfer
            else:
                budget = effective * dt
                for s in ordered_streams(streams,link["priority_tier"]):
                    name=s["name"]
                    bits=min(budget, backlog[sat][name])
                    backlog[sat][name]-=bits
                    remaining_to_remove=bits
                    queue=fifo[sat][name]
                    while remaining_to_remove>1e-7 and queue:
                        consumed=min(remaining_to_remove,queue[0][1])
                        queue[0][1]-=consumed
                        remaining_to_remove-=consumed
                        if queue[0][1]<=1e-7: queue.pop(0)
                    if bits>0: last_served_tier[sat][s["priority"]]=t+timedelta(seconds=dt)
                    sent[(sat,name)]+=bits
                    link["sent_bits"]+=bits
                    budget-=bits
                    if budget <= 0: break
                if budget < effective * dt: last_downlink[sat]=t+timedelta(seconds=dt)
            if link["remaining"] <= 0:
                schedule.append({"satellite":sat,"station":link["station"],
                                 "start_utc":iso(link["start"]),"end_utc":iso(t+timedelta(seconds=dt)),
                                 "downloaded_mbit":round(link["sent_bits"]/1e6,5),
                                 "reason":link["reason"],"priority_tier":link["priority_tier"],"pass_type":pass_type,
                                 "setup_minutes":setup_minutes,"acquisition_minutes":policy["acquisition_minutes"],
                                 "teardown_minutes":policy["teardown_minutes"]})
                just_finished_stations.add(link["station"])
                just_finished_satellites.add(sat)
                del active_links[sat]
        for sat in sats:
            total=sum(backlog[sat].values())
            peak[sat]=max(peak[sat],total)
            if total>capacity:
                violations[sat].add("MEMORY_OVERFLOW")
                # Real physical storage cannot exceed its limit. Drop oldest
                # lower-priority data first and explicitly account for losses.
                excess=total-capacity
                for stream in sorted(streams,key=lambda x:(x["priority"],-x["deadline_hours"])):
                    name=stream["name"]; queue=fifo[sat][name]
                    while excess>1e-7 and queue:
                        removed=min(excess,queue[0][1])
                        queue[0][1]-=removed
                        backlog[sat][name]-=removed
                        dropped[(sat,name)]+=removed
                        excess-=removed
                        if queue[0][1]<=1e-7: queue.pop(0)
                    if excess<=1e-7: break
                total=sum(backlog[sat].values())
            if total>capacity*(1-reserve): violations[sat].add("MEMORY_RESERVE_EXCEEDED")
            for s in streams:
                queue=fifo[sat][s["name"]]
                if queue and (t-queue[0][0]).total_seconds()>s["deadline_hours"]*3600:
                    violations[sat].add("DATA_AGE_"+s["name"])
            if (t-last_downlink[sat]).total_seconds()>max_gap: violations[sat].add("24H_CONTACT_GAP")
            last_sample[sat]={"satellite":sat,"time_utc":iso(t),"memory_mbit":round(total/1e6,4),
                "occupancy_fraction":round(total/capacity,5),
                "hours_to_usable_limit":round(max(0,capacity*(1-reserve)-total)/
                     max(1,sum(s["mean_rate_bps"] for s in streams))/3600,3),
                "alert":"CRITICAL" if total/capacity>=thresholds[2] else
                        "URGENT" if total/capacity>=thresholds[1] else
                        "WATCH" if total/capacity>=thresholds[0] else "NORMAL"}
            history.append(last_sample[sat])
        # Replan at every time step. Only begin contacts that fit entirely inside
        # a geometric window; enforce one link per station/satellite and daily DSN cap.
        busy_stations={link["station"] for link in active_links.values()} | just_finished_stations
        options=[]
        for sat in sats:
            if sat in active_links or sat in just_finished_satellites: continue
            total=sum(backlog[sat].values())
            base_rate=sum(s["mean_rate_bps"] for s in streams)
            hours_left=max(0,(capacity*(1-reserve)-total)/max(1,base_rate)/3600)
            since=(t-last_downlink[sat]).total_seconds()/3600
            age_risk=max(((t-fifo[sat][s["name"]][0][0]).total_seconds()/3600 /
                         s["deadline_hours"] if fifo[sat][s["name"]] else 0) for s in streams)
            urgency=max(total/(capacity*(1-reserve)),since/(max_gap/3600),age_risk)
            # Begin earlier when the next contact opportunity is scarce; also allow
            # a proactive fill-level trigger so short windows are not wasted.
            future = [c for c in contacts if c["satellite"]==sat and c["start"]>t]
            next_wait = min(((c["start"]-t).total_seconds()/3600 for c in future), default=float("inf"))
            if urgency < float(cfg["proactive_trigger_fraction"]) and since + next_wait < max_gap/3600: continue
            for c in contacts:
                if c["satellite"]!=sat or c["station"] in busy_stations or allowed.get(c["station"],True) is False: continue
                if not (c["start"]<=t<c["end"]): continue
                if any(a<t+timedelta(seconds=STEP) and b>t for a,b in unavailable.get(c["station"],[])): continue
                day=t.date().isoformat()
                remaining=cap_per_day-daily_used[day]
                # Reserve full contact time, including setup, from shared daily cap.
                available=min((c["end"]-t).total_seconds(),remaining,(end-t).total_seconds(),
                              (datetime.combine(t.date()+timedelta(days=1),datetime.min.time(),tzinfo=timezone.utc)-t).total_seconds())
                if available < (overhead_steps+min_steps)*STEP: continue
                tx_need=max(min_steps,math.ceil(total/(effective*STEP)))
                # Do not reserve more than needed for backlog plus near-term generation.
                steps=min(math.floor(available/STEP),overhead_steps+tx_need)
                if steps<overhead_steps+min_steps: continue
                options.append((urgency,-hours_left,-since,sat,c["station"],steps))
        # Greedy priority ordering: risk first; no global optimality guarantee.
        for urgency,neg_hours,neg_since,sat,station,steps in sorted(options,reverse=True):
            if sat in active_links or sat in just_finished_satellites or station in busy_stations: continue
            seconds=steps*STEP
            day=t.date().isoformat()
            if daily_used[day]+seconds>cap_per_day+1e-6: continue
            # Do not let a single scheduled contact cross a UTC day boundary.
            if (t+timedelta(seconds=seconds)).date()!=t.date():
                steps=min(steps,math.floor((datetime.combine(t.date()+timedelta(days=1),
                        datetime.min.time(),tzinfo=timezone.utc)-t).total_seconds()/STEP))
                seconds=steps*STEP
                if steps<overhead_steps+min_steps: continue
            # All windows must be usable for the full contact; station outages checked throughout.
            if any(a<t+timedelta(seconds=seconds) and b>t for a,b in unavailable.get(station,[])): continue
            active_links[sat]={"station":station,"start":t,"setup":setup_steps+acquisition_steps,
                               "priority_tier":choose_due_tier(streams,last_served_tier[sat],t),
                               "remaining":steps,"sent_bits":0.,
                               "reason":"adaptive_memory_deadline"}
            daily_used[day]+=seconds
            busy_stations.add(station)
        t+=timedelta(seconds=dt)
    for sat,link in active_links.items():
        schedule.append({"satellite":sat,"station":link["station"],"start_utc":iso(link["start"]),
                         "end_utc":iso(end),"downloaded_mbit":round(link["sent_bits"]/1e6,5),
                         "reason":"truncated_at_horizon","priority_tier":link["priority_tier"],"pass_type":pass_type,
                         "setup_minutes":setup_minutes,"acquisition_minutes":policy["acquisition_minutes"],
                         "teardown_minutes":policy["teardown_minutes"]})
    summary={"status":"PRELIMINARY_HYPOTHETICAL_NOT_BOOKED",
      "note":"2020 windows shifted by calendar to 2030, NOT repropagated. DSN cap is hypothetical; memory and environment events are assumptions. Greedy rolling heuristic, not a proven global optimum. FIFO age uses timestamps at 5-minute resolution.",
      "scenario_start_utc":iso(target),"scenario_end_utc":iso(end),
      "effective_downlink_bps":effective,"dsn_policy_status":policy["status"],
      "dsn_pass_type":pass_type,"dsn_setup_minutes":setup_minutes,
      "dsn_acquisition_minutes":policy["acquisition_minutes"],"dsn_teardown_minutes":policy["teardown_minutes"],
      "dsn_handover_overlap_minutes":policy["handover_overlap_minutes"],
      "dsn_handover_status":policy["handover_policy"],
      "emergency_antenna_response_minutes":policy["emergency_antenna_response_minutes"],
      "emergency_initial_continuous_hours":policy["emergency_initial_continuous_hours"],
      "emergency_policy_status":policy["emergency_policy"],"memory_capacity_mbit_per_satellite":capacity/1e6,
      "memory_allocation_policy":"volume_proportional_shared_pool_not_hard_partition",
      "memory_reserve_fraction":reserve,"satellites":{},"contacts":len(schedule),"dsn_assigned_hours":round(sum(daily_used.values())/3600,3)}
    volume_basis={x["name"]:x["mean_rate_bps"]*(end-target).total_seconds()/1e6 for x in streams}
    summary["memory_quotas_by_subsystem"]=volume_shares(volume_basis,capacity/1e6,reserve)
    summary["external_flows_status"]="Lunar relay and Earth uplink excluded until traffic volumes and contact geometry are specified"
    for sat in sats:
        summary["satellites"][sat]={"generated_mbit":round(sum(produced[(sat,s["name"])] for s in streams)/1e6,4),
           "downlinked_mbit":round(sum(sent[(sat,s["name"])] for s in streams)/1e6,4),
           "remaining_mbit":round(sum(backlog[sat].values())/1e6,4),
           "dropped_mbit":round(sum(dropped[(sat,x["name"])] for x in streams)/1e6,4),
           "initial_memory_mbit":round(capacity*initial/1e6,4),
           "peak_memory_mbit":round(peak[sat]/1e6,4),
           "peak_occupancy_fraction":round(peak[sat]/capacity,5),
           "contacts":sum(x["satellite"]==sat for x in schedule),
           "warnings":sorted(violations[sat]),
           "by_subsystem":{s["name"]:{"generated_mbit":round(produced[(sat,s["name"])]/1e6,4),
                   "downlinked_mbit":round(sent[(sat,s["name"])]/1e6,4),
                   "remaining_mbit":round(backlog[sat][s["name"]]/1e6,4),
                   "dropped_mbit":round(dropped[(sat,s["name"])]/1e6,4)} for s in streams}}
    # Post-run checks: never silently accept impossible storage or resource assignments.
    for sat in sats:
        for stream in streams:
            name=stream["name"]
            residual=produced[(sat,name)]+initial_bits-sent[(sat,name)]-dropped[(sat,name)]-backlog[sat][name]
            if abs(residual)>max(1e-3,produced[(sat,name)]*1e-9):
                raise AssertionError("Telemetry conservation failure: "+sat+"/"+name)
    for i,a in enumerate(schedule):
        a0=datetime.fromisoformat(a["start_utc"].replace("Z","+00:00"))
        a1=datetime.fromisoformat(a["end_utc"].replace("Z","+00:00"))
        for b in schedule[i+1:]:
            if a["satellite"]!=b["satellite"] and a["station"]!=b["station"]: continue
            b0=datetime.fromisoformat(b["start_utc"].replace("Z","+00:00"))
            b1=datetime.fromisoformat(b["end_utc"].replace("Z","+00:00"))
            if a0<b1 and b0<a1: raise AssertionError("Conflicting station/satellite contacts")
    out=Path(output_dir or ROOT/"outputs")
    out.mkdir(parents=True,exist_ok=True)
    (out/"adaptive_storage_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    for name,rows in [("adaptive_storage_history.csv",history),("adaptive_contact_schedule.csv",schedule)]:
        with (out/name).open("w",newline="",encoding="utf-8") as f:
            if rows:
                w=csv.DictWriter(f,fieldnames=list(rows[0]))
                w.writeheader();w.writerows(rows)
    return summary

if __name__=="__main__":
    print(json.dumps(plan(),indent=2))
