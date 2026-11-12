"""Parametric Earth downlink RF/EPS/TCS trade with explicit scenario assumptions."""
import csv
import json
import math
from pathlib import Path
from .antenna_link_budget import antenna
from .link_budget import evaluate_link

def trade(config,rate_bps,contact_hours=1):
    if rate_bps<=0 or contact_hours<0:raise ValueError("Invalid rate or duration")
    required=["frequency_hz","distance_km","tx_diameters_m","tx_efficiency",
              "rx_gt_db_per_k","required_ebn0_db","losses_db","margin_db",
              "pa_efficiency","electronics_w"]
    missing=[k for k in required if config.get(k) is None]
    if missing:return {"status":"MISSING_RF_INPUTS","missing_inputs":missing,"cases":[]}
    if not config["tx_diameters_m"]:raise ValueError("No antenna candidates")
    rows=[]
    for diameter in config["tx_diameters_m"]:
        a=antenna(float(config["frequency_hz"]),float(diameter),float(config["tx_efficiency"]),
                  float(config.get("pointing_error_deg",0)))
        link=evaluate_link({"distance_km":config["distance_km"],
            "frequency_hz":config["frequency_hz"],
            "tx_gain_dbi":a["gain_dbi"]+a["pointing_loss_db"],
            "rx_gt_db_per_k":config["rx_gt_db_per_k"],
            "data_rate_bps":rate_bps,
            "required_ebn0_db":config["required_ebn0_db"],
            "losses_db":config["losses_db"],"margin_db":config["margin_db"],
            "pa_efficiency":config["pa_efficiency"],
            "electronics_w":config["electronics_w"]})
        rows.append({"diameter_m":float(diameter),"gain_dbi":a["gain_dbi"],
                     "beamwidth_deg":a["beamwidth_3db_deg"],
                     "pointing_loss_db":a["pointing_loss_db"],
                     "required_rf_w":link["minimum_tx_rf_w_with_design_margin"],
                     "tx_dc_w":link["estimated_tx_dc_w"],
                     "tx_heat_w":link["estimated_dissipated_heat_w"],
                     "contact_energy_wh":link["estimated_tx_dc_w"]*contact_hours
                     if link["estimated_tx_dc_w"] is not None else None})
    return {"status":"ILLUSTRATIVE_RF_TRADE_NOT_HARDWARE_SELECTION",
            "rate_bps":rate_bps,"contact_hours":contact_hours,
            "assumptions":config,"cases":rows}

def run(config_path="data/rf_trade_assumptions.json",rate_bps=256000,
        contact_hours=1,output_dir="outputs"):
    config=json.loads(Path(config_path).read_text(encoding="utf-8"))
    result=trade(config,rate_bps,contact_hours)
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    (out/"rf_trade_study.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    if result["cases"]:
        with (out/"rf_trade_study.csv").open("w",newline="",encoding="utf-8") as f:
            writer=csv.DictWriter(f,fieldnames=list(result["cases"][0]))
            writer.writeheader();writer.writerows(result["cases"])
    return result

if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--config",default="data/rf_trade_assumptions.json")
    p.add_argument("--rate-bps",type=float,default=256000)
    p.add_argument("--contact-hours",type=float,default=1)
    p.add_argument("--output-dir",default="outputs")
    a=p.parse_args()
    print(json.dumps(run(a.config,a.rate_bps,a.contact_hours,a.output_dir),indent=2))
