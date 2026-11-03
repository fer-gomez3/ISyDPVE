"""Preliminary Earth X-band downlink budget. All losses are positive dB magnitudes."""
import json
import math
from pathlib import Path

C=299792458.0
K_DB=-228.6

def evaluate_link(p):
    required=["distance_km","frequency_hz","tx_gain_dbi","rx_gt_db_per_k","data_rate_bps","required_ebn0_db","losses_db","margin_db"]
    missing=[k for k in required if p.get(k) is None]
    if missing:
        return {"status":"MISSING_INPUTS","missing_inputs":missing,"note":"No RF power or feasibility claim until inputs are supplied."}
    distance=float(p["distance_km"])*1000
    freq=float(p["frequency_hz"])
    rate=float(p["data_rate_bps"])
    if min(distance,freq,rate)<=0:raise ValueError("Distance, frequency and bit rate must be positive")
    losses=float(p["losses_db"])
    margin=float(p["margin_db"])
    if losses<0 or margin<0:raise ValueError("Losses and margin must be nonnegative")
    fspl=20*math.log10(4*math.pi*distance*freq/C)
    required_eirp=(float(p["required_ebn0_db"])+margin+10*math.log10(rate)
                   +fspl+losses-float(p["rx_gt_db_per_k"])-228.6)
    tx_dbw=required_eirp-float(p["tx_gain_dbi"])
    required_rf_w=10**(tx_dbw/10)
    actual=p.get("tx_rf_w")
    available_ebn0=None
    achieved_margin=None
    if actual is not None:
        if float(actual)<=0:raise ValueError("tx_rf_w must be positive")
        actual_eirp=10*math.log10(float(actual))+float(p["tx_gain_dbi"])
        available_ebn0=actual_eirp-fspl-losses+float(p["rx_gt_db_per_k"])+228.6-10*math.log10(rate)
        achieved_margin=available_ebn0-float(p["required_ebn0_db"])
    efficiency=p.get("pa_efficiency")
    electronics=p.get("electronics_w")
    dc=None;heat=None
    if efficiency is not None:
        efficiency=float(efficiency)
        if not 0<efficiency<=1:raise ValueError("pa_efficiency must be in (0,1]")
        if electronics is not None:
            if float(electronics)<0:raise ValueError("electronics_w must be nonnegative")
            rf_for_power=float(actual) if actual is not None else required_rf_w
            dc=rf_for_power/efficiency+float(electronics)
            heat=dc-rf_for_power
    return {"status":"PRELIMINARY","distance_km":float(p["distance_km"]),
        "frequency_hz":freq,"data_rate_bps":rate,
        "free_space_path_loss_db":fspl,"other_losses_db":losses,
        "required_eirp_dbw":required_eirp,"minimum_tx_rf_w_with_design_margin":required_rf_w,
        "available_ebn0_db":available_ebn0,"achieved_margin_db":achieved_margin,
        "estimated_tx_dc_w":dc,"estimated_dissipated_heat_w":heat,
        "note":"Assumes constant positive path losses and provided receiving G/T. RF gain is inclusive of transmit-line losses only if user incorporated them in losses_db. Required Eb/N0 must be selected for the actual modulation, FEC and BER/FER. No DSN booking or availability guaranteed."}

def from_file(path="data/link_budget_inputs.json"):
    return evaluate_link(json.loads(Path(path).read_text(encoding="utf-8")))

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",default="data/link_budget_inputs.json")
    parser.add_argument("--output",default="outputs/link_budget.json")
    a=parser.parse_args()
    result=from_file(a.input)
    dest=Path(a.output);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
