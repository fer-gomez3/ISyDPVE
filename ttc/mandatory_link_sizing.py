"""Contact-driven mandatory transfer and RF sizing for SELENA.
Missing RF inputs produce explicit TBD, never fabricated antenna dimensions.
"""
import csv
import json
import math
from pathlib import Path
from .adaptive_storage import ROOT
from .antenna_link_budget import antenna, link

KB=1.380649e-23

def rf_trade(rate_bps, case):
    required=("frequency_hz","distance_m","rx_diameter_m","rx_efficiency",
              "tx_efficiency","tx_line_efficiency","receiver_noise_temperature_K",
              "required_Eb_N0_dB","additional_losses_dB","min_diameter_m",
              "max_diameter_m","diameter_step_m","min_power_w","max_power_w",
              "power_step_w")
    missing=[k for k in required if case.get(k) is None]
    if missing: return {"status":"TBD_RF_INPUTS","missing":missing}
    if rate_bps<=0:return {"status":"NO_TRAFFIC"}
    f=case["frequency_hz"]
    rx=antenna(f,case["rx_diameter_m"],case["rx_efficiency"],
               case.get("rx_pointing_error_deg") or 0)
    options=[]
    d=case["min_diameter_m"]
    while d<=case["max_diameter_m"]+1e-9:
        tx=antenna(f,d,case["tx_efficiency"],case.get("tx_pointing_error_deg") or 0)
        # Pr/(k T R) >= required Eb/N0, including explicit implementation losses.
        needed_w=(10**((case["required_Eb_N0_dB"]+case["additional_losses_dB"])/10)
                  *KB*case["receiver_noise_temperature_K"]*rate_bps)
        one_w=link(f,case["distance_m"],1.,tx["gain_linear"],
                   case["tx_line_efficiency"],rx["gain_linear"],
                   tx["pointing_loss_db"],rx["pointing_loss_db"])["received_power_w"]
        required_power=needed_w/one_w
        p=max(case["min_power_w"],math.ceil((required_power-1e-12)/case["power_step_w"])*case["power_step_w"])
        if p<=case["max_power_w"]+1e-9:
            options.append({"diameter_m":round(d,6),"rf_power_w":round(p,6),
                            "gain_dbi":tx["gain_dbi"],"beamwidth_deg":tx["beamwidth_3db_deg"],
                            "required_rf_power_w":required_power,
                            "eb_n0_margin_db":10*math.log10(one_w*p/needed_w)})
        d+=case["diameter_step_m"]
    if not options:return {"status":"NO_FEASIBLE_ANTENNA_POWER_COMBINATION"}
    # Two separate optima: diameter and power cannot both be minimized simultaneously.
    return {"status":"FEASIBLE_PRELIMINARY","minimum_diameter":min(options,key=lambda x:(x["diameter_m"],x["rf_power_w"])),
            "minimum_power":min(options,key=lambda x:(x["rf_power_w"],x["diameter_m"])),
            "pareto_options":options}

def size_contacts(schedule_path=None,summary_path=None,telemetry_path=None,
                  rf_inputs_path=None,output_dir=None):
    out=Path(output_dir or ROOT/"outputs");out.mkdir(parents=True,exist_ok=True)
    summary=json.loads(Path(summary_path or out/"adaptive_storage_summary.json").read_text())
    tel=json.loads(Path(telemetry_path or ROOT/"data"/"telemetry_detailed_scenario.json").read_text())
    rf=json.loads(Path(rf_inputs_path or ROOT/"data"/"antenna_link_inputs.json").read_text())
    with Path(schedule_path or out/"adaptive_contact_schedule.csv").open(newline="") as f:
        contacts=list(csv.DictReader(f))
    # Actual contact durations are measured, rather than assigning fictional window lengths.
    from datetime import datetime
    from .telemetry_generation import calculate,apply_computed_rates
    from .transfer_planning import stream_requirements
    inputs=json.loads((ROOT/"data"/"telemetry_generation_inputs.json").read_text())
    apply_computed_rates(tel,calculate(inputs)["subsystems"])
    streams=stream_requirements(tel)
    from .priority_memory_policy import ordered_streams
