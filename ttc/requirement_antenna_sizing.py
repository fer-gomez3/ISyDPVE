"""Requirement-driven SELENA Earth downlink antenna sizing.

No fixed diameter candidates. Diameter is solved from required rate, RF power
budget and link assumptions. Missing RF power stays TBD.
Run: python -m ttc.requirement_antenna_sizing
"""
import argparse
import csv
import json
import math
from pathlib import Path

from .antenna_link_budget import C, antenna
from .link_budget import evaluate_link

ROOT = Path(__file__).resolve().parents[1]

def size(cfg, backlog_mbit, useful_minutes, generation_bps=0, rf_power_w=None):
    if backlog_mbit < 0 or useful_minutes <= 0 or generation_bps < 0:
        raise ValueError("Backlog, useful duration and generation must be valid")
    link = cfg["earth_downlink"]
    overhead = float(cfg.get("protocol_overhead_fraction", 0.2))
    if not 0 <= overhead < 1:
        raise ValueError("Invalid overhead")
    useful_s = useful_minutes * 60
    required_net_bps = backlog_mbit * 1e6 / useful_s + generation_bps
    gross_bps = required_net_bps / (1 - overhead)
    result = {"status": "MISSING_RF_POWER_BUDGET", "backlog_mbit": backlog_mbit,
              "useful_minutes": useful_minutes, "generation_bps": generation_bps,
              "required_net_bps": required_net_bps, "required_gross_bps": gross_bps,
              "diameter_m": None, "gain_dbi": None, "beamwidth_deg": None,
              "tx_dc_w": None, "tx_heat_w": None, "contact_energy_wh": None,
              "assumption_status": "PRELIMINARY_NOT_FLIGHT_VALIDATED"}
    power = rf_power_w if rf_power_w is not None else cfg.get("max_tx_rf_w")
    if power is None:
        return result
    power = float(power)
    if power <= 0:
        raise ValueError("RF power budget must be positive")
    required = ("frequency_hz", "distance_km", "tx_efficiency",
                "rx_gt_db_per_k", "required_ebn0_db", "losses_db", "margin_db")
    missing = [k for k in required if link.get(k) is None]
    if missing:
        result.update(status="MISSING_LINK_INPUTS", missing_inputs=missing)
        return result
    # Evaluate link with 0 dBi TX gain to obtain the EIRP requirement.
    budget = evaluate_link(dict(distance_km=link["distance_km"],
        frequency_hz=link["frequency_hz"], tx_gain_dbi=0,
        rx_gt_db_per_k=link["rx_gt_db_per_k"], data_rate_bps=gross_bps,
        required_ebn0_db=link["required_ebn0_db"], losses_db=link["losses_db"],
        margin_db=link["margin_db"]))
    required_gain_db = budget["required_eirp_dbw"] - 10 * math.log10(power)
    wavelength = C / float(link["frequency_hz"])
    efficiency = float(link["tx_efficiency"])
    pointing_error = float(link.get("pointing_error_deg", 0))
    if not 0 < efficiency <= 1 or pointing_error < 0:
        raise ValueError("Invalid aperture efficiency or pointing error")
    # Pointing loss depends on beamwidth, which itself depends on diameter.
    # Find the smallest diameter meeting required EIRP by scanning then bisection.
    def margin(d):
        a = antenna(float(link["frequency_hz"]), d, efficiency, pointing_error)
        return a["gain_dbi"] + a["pointing_loss_db"] - required_gain_db
    lo = 1e-5
    hi = 0.01
    while hi < 100 and margin(hi) < 0:
        hi *= 1.25
    if margin(hi) < 0:
        result.update(status="NO_FEASIBLE_APERTURE_WITHIN_100_M")
        return result
    # At large pointing errors the gain may be nonmonotonic; scan from small
    # diameters to capture the first feasible crossing.
    last = lo
    crossing = None
    for i in range(1, 10001):
        d = lo * (hi / lo) ** (i / 10000)
        if margin(d) >= 0:
            crossing = (last, d)
            break
        last = d
    if crossing is None:
        result.update(status="NO_FEASIBLE_APERTURE")
        return result
    left, right = crossing
    for _ in range(65):
        mid = (left + right) / 2
        if margin(mid) >= 0:
            right = mid
        else:
            left = mid
    a = antenna(float(link["frequency_hz"]), right, efficiency, pointing_error)
    pa_eta = link.get("pa_efficiency")
    electronics = link.get("electronics_w")
    dc = None if pa_eta is None or electronics is None else power / float(pa_eta) + float(electronics)
    heat = None if dc is None else dc - power
    result.update(status="PRELIMINARY_SIZED", rf_power_budget_w=power,
        required_gain_dbi=required_gain_db, diameter_m=right,
        gain_dbi=a["gain_dbi"], pointing_loss_db=a["pointing_loss_db"],
        beamwidth_deg=a["beamwidth_3db_deg"], tx_dc_w=dc,
        tx_heat_w=heat, contact_energy_wh=None if dc is None else dc * useful_minutes / 60,
        note="Aperture diameter only; mechanical envelope, mass, gimbal, EPS and TCS totals remain TBD")
    return result

def run(backlog_mbit=198.87, useful_minutes=20, generation_bps=2301.74,
        rf_power_w=None, config_path=None, output_dir="outputs/antenna_sizing"):
    cfg = json.loads(Path(config_path or ROOT / "data" / "communications_budget_inputs.json").read_text(encoding="utf-8"))
    result = size(cfg, backlog_mbit, useful_minutes, generation_bps, rf_power_w)
    dest = Path(output_dir)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "antenna_sizing.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    with (dest / "antenna_sizing.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(result))
        writer.writeheader()
        writer.writerow(result)
    return result

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--backlog-mbit", type=float, default=198.87)
    p.add_argument("--useful-minutes", type=float, default=20)
    p.add_argument("--generation-bps", type=float, default=2301.74)
    p.add_argument("--rf-power-w", type=float)
    p.add_argument("--config")
    p.add_argument("--output-dir", default="outputs/antenna_sizing")
    a = p.parse_args()
    print(json.dumps(run(a.backlog_mbit, a.useful_minutes, a.generation_bps,
                         a.rf_power_w, a.config, a.output_dir), indent=2))
