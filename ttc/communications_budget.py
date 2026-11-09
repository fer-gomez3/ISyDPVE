"""SELENA communications-only aperture and electrical budget.

No mass estimation. Missing hardware powers remain unknown, never zero.
Inputs are illustrative until subsystem owners approve them.
"""
import json
import math
from pathlib import Path
from .antenna_link_budget import antenna
from .link_budget import evaluate_link
from .adaptive_storage import ROOT

MODES = {
    "off": (),
    "standby": ("standby_w",),
    "lunar_rx": ("standby_w", "lunar_receiver_w", "lunar_processing_w", "memory_interface_w", "gimbal_tracking_w"),
    "earth_tx": ("standby_w", "tx_dc_w", "memory_interface_w", "gimbal_tracking_w"),
    "simultaneous": ("standby_w", "lunar_receiver_w", "lunar_processing_w",
                     "memory_interface_w", "tx_dc_w", "gimbal_tracking_w"),
    "slew_acquisition": ("standby_w", "gimbal_slew_w"),
}

def power_modes(powers, durations_hours=None):
    """Power is additive only for independent incremental loads; shared loads appear once."""
    durations_hours = durations_hours or {}
    unknown = sorted(set(durations_hours) - set(MODES))
    if unknown:
        raise ValueError("Unknown modes: " + ", ".join(unknown))
    if any(not math.isfinite(float(v)) or float(v) < 0 for v in durations_hours.values()):
        raise ValueError("Durations must be finite and nonnegative")
    if sum(float(v) for v in durations_hours.values()) > 24 + 1e-9:
        raise ValueError("Mode durations exceed 24 hours")
    result = {}
    for mode, fields in MODES.items():
        missing = [f for f in fields if powers.get(f) is None]
        values = [float(powers[f]) for f in fields if powers.get(f) is not None]
        if any(not math.isfinite(v) or v < 0 for v in values):
            raise ValueError("Power must be finite and nonnegative")
        watts = None if missing else sum(values)
        hours = float(durations_hours.get(mode, 0))
        result[mode] = {"power_w": watts, "missing_inputs": missing,
                        "duration_hours": hours, "energy_wh": None if watts is None else watts * hours}
    scheduled_hours = sum(v["duration_hours"] for v in result.values())
    unallocated_hours = max(0.0, 24.0 - scheduled_hours)
    active = [v for v in result.values() if v["duration_hours"] > 0]
    total_energy = None if unallocated_hours > 1e-9 or any(v["energy_wh"] is None for v in active) else sum(v["energy_wh"] for v in active)
    peak = None if any(v["power_w"] is None for v in active) else max((v["power_w"] for v in active), default=0)
    return {"modes": result, "scheduled_hours": scheduled_hours, "unallocated_hours": unallocated_hours, "energy_wh_per_day": total_energy,
            "average_w_over_24h": None if total_energy is None else total_energy / 24,
            "peak_w_in_scheduled_modes": peak,
            "status": "INCOMPLETE_DAILY_SCHEDULE" if unallocated_hours > 1e-9 else ("INCOMPLETE_POWER_INPUTS" if any(v["missing_inputs"] for v in active) else "CALCULATED_FROM_INPUTS")}

def antenna_options(rf, rate_bps, diameters_m, max_tx_rf_w=None):
    if rate_bps <= 0 or not math.isfinite(rate_bps):
        raise ValueError("Invalid rate")
    cases = []
    for diameter in diameters_m:
        a = antenna(rf["frequency_hz"], float(diameter), rf["tx_efficiency"], rf.get("pointing_error_deg", 0))
        result = evaluate_link({
            "distance_km": rf.get("distance_km"), "frequency_hz": rf.get("frequency_hz"),
            "tx_gain_dbi": a["gain_dbi"] + a["pointing_loss_db"],
            "rx_gt_db_per_k": rf.get("rx_gt_db_per_k"), "data_rate_bps": rate_bps,
            "required_ebn0_db": rf.get("required_ebn0_db"), "losses_db": rf.get("losses_db"),
            "margin_db": rf.get("margin_db"), "pa_efficiency": rf.get("pa_efficiency"),
            "electronics_w": rf.get("electronics_w")
        })
        required = result.get("minimum_tx_rf_w_with_design_margin")
        feasible = None if max_tx_rf_w is None or required is None else required <= max_tx_rf_w
        cases.append({"diameter_cm": diameter * 100, "gain_dbi": a["gain_dbi"],
                      "beamwidth_deg": a["beamwidth_3db_deg"], "pointing_loss_db": a["pointing_loss_db"],
                      "required_rf_w": required, "tx_dc_w": result.get("estimated_tx_dc_w"),
                      "within_rf_power_cap": feasible, "link_status": result["status"]})
    eligible = [x for x in cases if x["within_rf_power_cap"] is True]
    return {"cases": cases,
            "smallest_tested_feasible_diameter_cm": min((x["diameter_cm"] for x in eligible), default=None),
            "selection_status": "NO_POWER_CAP_OR_LINK_INPUTS" if max_tx_rf_w is None or any(x["within_rf_power_cap"] is None for x in cases) else ("FEASIBLE_WITHIN_TESTED_GRID" if eligible else "NO_FEASIBLE_TESTED_DIAMETER"),
            "note": "Grid candidates only; no hardware mass, lunar uplink closure or flight qualification."}

def run(config_path=None, output_path=None):
    config = json.loads(Path(config_path or ROOT / "data" / "communications_budget_inputs.json").read_text(encoding="utf-8"))
    rf = config["earth_downlink"]
    opts = antenna_options(rf, config["downlink_gross_bps"], config["diameters_m"], config.get("max_tx_rf_w"))
    # Power budget is only complete when all selected component draws are specified.
    selected = config.get("selected_diameter_m")
    match = next((c for c in opts["cases"] if selected is not None and abs(c["diameter_cm"] - selected * 100) < 1e-8), None)
    powers = dict(config["component_powers_w"])
    if match and match["tx_dc_w"] is not None:
        # TX electrical load includes its own radio electronics; do not duplicate.
        powers["tx_dc_w"] = match["tx_dc_w"]
    power = power_modes(powers, config.get("mode_hours_per_day", {}))
    from .antenna_sizing import minimum_diameter
    sizing = minimum_diameter(rf, config["downlink_gross_bps"], config.get("max_tx_rf_w"))
    result = {"status": "PRELIMINARY_NOT_FLIGHT_VALIDATED", "antenna": opts,
              "minimum_required_antenna": sizing,
              "selected_diameter_cm": None if selected is None else selected * 100,
              "communications_power": power,
              "lunar_uplink": {"status": "NOT_IN_DOCUMENTED_CDH_SCOPE", "note": "Surface PNT reception is a Payload service; lunar-to-orbit relay is not a confirmed requirement."},
              "report_interfaces": config.get("report_interfaces"),
              "scope": "Communications power only, no spacecraft EPS generation or antenna mass"}
    if output_path:
        out = Path(output_path); out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result

if __name__ == "__main__":
    print(json.dumps(run(output_path=ROOT / "outputs" / "communications_budget.json"), indent=2))
