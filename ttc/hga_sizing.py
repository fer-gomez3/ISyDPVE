"""Preliminary dish gain and downlink feasibility, NOT selected flight hardware."""
import json
import math
from pathlib import Path
from .link_budget import evaluate_link, C

def calculate(antenna, link):
    d=float(antenna["diameter_m"])
    eta=float(antenna["aperture_efficiency"])
    f=float(antenna["frequency_hz"])
    if d<=0 or f<=0 or not 0<eta<=1: raise ValueError("Invalid HGA diameter, frequency or efficiency")
    gain_linear=eta*(math.pi*d*f/C)**2
    gain=10*math.log10(gain_linear)
    p={**link,"frequency_hz":f,"tx_gain_dbi":gain,"data_rate_bps":antenna["downlink_bps"]}
    result=evaluate_link(p)
    required_gain=None
    if result["status"]=="PRELIMINARY":
        required_gain=gain+10*math.log10(result["minimum_tx_rf_w_with_design_margin"]/float(link.get("tx_rf_w") or result["minimum_tx_rf_w_with_design_margin"]))
    required_diameter=None if required_gain is None else C/(math.pi*f)*math.sqrt(10**(required_gain/10)/eta)
    return {"status":"PRELIMINARY_HYPOTHETICAL","diameter_m":d,"aperture_efficiency_assumed":eta,"calculated_idealized_gain_dbi":gain,"mass_reflector_feed_kg_nominal":antenna["reflector_feed_mass_kg_nominal"],"mass_reflector_feed_kg_range":[antenna["reflector_feed_mass_kg_min"],antenna["reflector_feed_mass_kg_max"]],"gimbal_mass_kg_in_structures_not_ttc":antenna["gimbal_mass_kg"],"ttc_obdh_mass_allocation_kg":antenna["ttc_obdh_mass_allocation_kg"],"other_ttc_obdh_mass_available_kg_before_margins":antenna["ttc_obdh_mass_allocation_kg"]-antenna["reflector_feed_mass_kg_nominal"],"link":result,"required_gain_dbi_for_assumed_rf_power":required_gain,"minimum_diameter_m_for_assumed_rf_power":required_diameter,"warning":"Gain assumes circular aperture and efficiency, neglects pointing/polarization unless in link losses. Check 7.2 GHz uplink separately. Required diameter uses tx_rf_w if specified; otherwise it is trivially equal to input diameter and NOT a sizing constraint."}

def from_files(antenna_path="data/hga_preliminary_design.json",link_path="data/link_budget_inputs.json"):
    return calculate(json.loads(Path(antenna_path).read_text()),json.loads(Path(link_path).read_text()))

if __name__=="__main__":
    print(json.dumps(from_files(),indent=2))
