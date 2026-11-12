"""Deterministic per-satellite backlog and priority downlink simulation.

Uses hypothetical allocated windows, not confirmed DSN bookings.

Model
  * Every stream generates data at a constant mean rate and is delivered first-in first-out.
  * Outside a contact (and during the setup part of a contact) data only accumulates.
  * During the useful part of a contact the simulation advances in short steps: data generated
    in a step joins the backlog and the step's capacity (effective rate x step) is spent on
    streams in priority order (highest priority first, then tightest deadline). Data generated
    during the contact is therefore transmitted as soon as capacity is available.
  * Because delivery is FIFO and generation is constant, the age of the oldest undelivered bit
    of a stream is exactly backlog / generation rate. A stream is flagged when that age ever
    exceeds its maximum data age.

This is a time-discretized approximation (default 60 s steps). Ages are checked at step
boundaries, so a maximum age can be underestimated by up to one step. On the full scenario,
steps of 60, 30, 10 and 1 s give identical downloaded volumes and identical deadline-risk
sets; maximum ages differ by at most 0.016 h.
"""
import csv
from datetime import datetime, timedelta
import json
from pathlib import Path
from .contact_analysis import load_contacts
from .dsn_allocation import allocate
from .parameters import apply_policy
from .telemetry_generation import calculate as calculate_telemetry, apply_computed_rates
from .transfer_planning import stream_requirements

STEP_SECONDS = 60.0


def run(cfg, contacts, policy, step_seconds=STEP_SECONDS):
    rows = allocate(contacts, policy)
    overhead = float(cfg["policy"]["protocol_overhead_fraction"])
    rate = cfg["policy"].get("net_downlink_bps")
    if rate is None:
        return {"status": "MISSING_DOWNLINK_RATE", "contacts": [], "satellites": {}}
    rate = float(rate)
    if rate <= 0 or not 0 <= overhead < 1:
        raise ValueError("Invalid downlink rate/overhead")
    if step_seconds <= 0:
        raise ValueError("step_seconds must be positive")
    effective = rate * (1 - overhead)
    streams = stream_requirements(cfg)
    if any(s["mean_rate_bps"] is None for s in streams):
        raise ValueError("Unknown telemetry rate")
    setup = float(policy.get("setup_minutes", 5)) * 60
    start = min(c["start"] for c in contacts)
    end = max(c["end"] for c in contacts)
    horizon = (end - start).total_seconds()
    order = sorted(streams, key=lambda x: (-x["priority"], x["deadline_hours"], x["name"]))
    satellites = {}
    log = []
    for sat in sorted({c["satellite"] for c in contacts}):
        backlog = {s["name"]: 0. for s in streams}
        produced = {s["name"]: 0. for s in streams}
        sent = {s["name"]: 0. for s in streams}
        max_age = {s["name"]: 0. for s in streams}
        gen = {s["name"]: s["mean_rate_bps"] for s in streams}
        state = {"t": 0.0, "peak": 0.}

        def accumulate(dt):
            for s in streams:
                name = s["name"]
                bits = gen[name] * dt
                backlog[name] += bits
                produced[name] += bits

        def observe():
            for s in streams:
                name = s["name"]
                if gen[name] > 0:
                    max_age[name] = max(max_age[name], backlog[name] / gen[name])
            state["peak"] = max(state["peak"], sum(backlog.values()))

        def idle(until):
            dt = until - state["t"]
            if dt < -1e-6:
                raise ValueError("Overlapping candidate windows for same satellite")
            accumulate(max(0.0, dt))
            state["t"] = max(state["t"], until)
            observe()

        windows = sorted((w for w in rows if w["satellite"] == sat and w["useful_tx_seconds"] > 0),
                         key=lambda w: w["candidate_start_utc"])
        for w in windows:
            a = (datetime.fromisoformat(w["candidate_start_utc"]) - start).total_seconds()
            tx_start = a + setup
            tx_end = tx_start + w["useful_tx_seconds"]
            idle(tx_start)
            before = sum(backlog.values())
            used = 0.
            t = tx_start
            while t < tx_end - 1e-9:
                dt = min(step_seconds, tx_end - t)
                accumulate(dt)
                capacity = effective * dt
                for s in order:
                    name = s["name"]
                    take = min(backlog[name], capacity)
                    backlog[name] -= take
                    sent[name] += take
                    used += take
                    capacity -= take
                    if backlog[name] < 1e-7:
                        backlog[name] = 0.
                    if capacity <= 0:
                        break
                t += dt
                state["t"] = t
                observe()
            log.append({"satellite": sat, "station": w["station"],
                        "start_utc": (start + timedelta(seconds=tx_start)).isoformat(),
                        "end_utc": (start + timedelta(seconds=tx_end)).isoformat(),
                        "useful_seconds": w["useful_tx_seconds"],
                        "capacity_mbit": w["useful_tx_seconds"] * effective / 1e6,
                        "downloaded_mbit": used / 1e6,
                        "backlog_before_mbit": before / 1e6,
                        "backlog_after_mbit": sum(backlog.values()) / 1e6})
        idle(horizon)
        risk = sorted(s["name"] for s in streams if max_age[s["name"]] > s["deadline_hours"] * 3600 + 1e-6)
        satellites[sat] = {"generated_mbit": sum(produced.values()) / 1e6,
            "downloaded_mbit": sum(sent.values()) / 1e6,
            "remaining_mbit": sum(backlog.values()) / 1e6,
            "peak_backlog_mbit": state["peak"] / 1e6,
            "deadline_risk_streams": risk,
            "by_stream": {s["name"]: {"generated_mbit": produced[s["name"]] / 1e6,
                "downloaded_mbit": sent[s["name"]] / 1e6,
                "remaining_mbit": backlog[s["name"]] / 1e6,
                "max_data_age_hours": max_age[s["name"]] / 3600,
                "deadline_hours": s["deadline_hours"]} for s in streams}}
    log.sort(key=lambda c: (c["start_utc"], c["satellite"]))
    return {"status": "HYPOTHETICAL_SCENARIO", "rate_bps": rate, "effective_data_bps": effective,
            "step_seconds": step_seconds,
            "note": "Historical 2020 geometry shifted to 2030; not DSN booked, not orbit propagation. FIFO delivery by stream priority; data generated during a contact is transmitted when capacity is available. Time-discretized approximation (see step_seconds); deadline ages are checked at step boundaries. Deadlines are checked against the exact age of the oldest undelivered bit. No event bursts or slew model.",
            "contacts": log, "satellites": satellites}


def compute(telemetry_path="data/telemetry_detailed_scenario.json",
            contacts_path="data/contacts_master.csv",
            policy_path="data/dsn_allocation_scenario.json", output_dir="outputs",
            telemetry_inputs_path="data/telemetry_generation_inputs.json"):
    cfg = json.loads(Path(telemetry_path).read_text(encoding="utf-8"))
    cfg["policy"] = apply_policy(cfg.get("policy", {}))
    if any(s.get("rate_bps") is None for s in cfg["streams"]):
        # Rates are never stored in the scenario file: derive them from the sensor inventories.
        inputs = json.loads(Path(telemetry_inputs_path).read_text(encoding="utf-8"))
        apply_computed_rates(cfg, calculate_telemetry(inputs)["subsystems"])
    policy = apply_policy(json.loads(Path(policy_path).read_text(encoding="utf-8")))
    result = run(cfg, load_contacts(contacts_path), policy)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "downlink_simulation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if result["contacts"]:
        with (out / "downlink_contacts.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(result["contacts"][0]))
            w.writeheader()
            w.writerows(result["contacts"])
    return result


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
