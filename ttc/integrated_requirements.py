"""Integrated TT&C requirements outputs from the contacts ASSIGNED by the DSN scheduler.

Thin wrapper over ``ttc.contact_rf_budget``: antenna, RF power, DC consumption,
heat and energy per contact, with coherence checks against EPS, Thermal and
ADCS data. No fixed antenna candidates, no antenna mass, no data reduction;
candidate visibility windows are never used.
"""
import json
from pathlib import Path

from .contact_rf_budget import run as rf_budget_run


def build(output_dir, config_path="data/communications_budget_inputs.json",
          telemetry_path=None, rf_power_w=None, diameter_m=None, overrides=None):
    out = Path(output_dir)
    gen_path = Path(telemetry_path) if telemetry_path else out / "telemetry_generation.json"
    rate = None
    if gen_path.exists():
        rate = json.loads(gen_path.read_text(encoding="utf-8")).get("total_rate_bps_per_spacecraft")
    ov = {**(overrides or {})}
    if rf_power_w is not None:
        ov["max_tx_rf_w"] = rf_power_w
    if diameter_m is not None:
        ov["diameter_m"] = diameter_m
    res = rf_budget_run(out, overrides=ov, generation_bps=rate, make_figures=True)
    status = res["status"]
    if status in ("MISSING_ASSIGNED_CONTACTS", "NOT_ASSIGNED_CONTACTS"):
        status = "MISSING_CONTACT_DURATIONS"
    result = {"status": status, "source": "assigned_contacts_from_dsn_scheduler",
              "satellite_generation_bps": rate, "cases": len(res.get("contacts") or []),
              "missing_inputs": res.get("missing_parameters"),
              "design": res.get("design"), "totals": res.get("totals"), "verdict": res.get("verdict"),
              "rf_budget_files": {"summary": "rf_budget_summary.json", "by_contact": "rf_budget_by_contact.csv",
                                  "energy_by_day": "rf_budget_energy_by_day.csv", "checks": "rf_coherence_checks.csv"},
              "dsn_note": "Sized on contacts assigned by ttc.dsn_scheduler (hypothetical allocation, not DSN bookings); "
                          "candidate visibility windows are not used.",
              "geometry_note": "Historical visibility shifted to 2030 is not mission propagation."}
    (out / "integrated_antenna_eps_thermal.json").write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    return result
