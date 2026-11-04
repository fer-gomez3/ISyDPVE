"""Compatibility wrapper for the validated-sign-convention link-budget engine."""
from .link_budget import evaluate_link

def evaluate(link, contact_hours=None):
    r=evaluate_link(link)
    missing=r.get("missing_inputs",[])
    result={"status":"INCOMPLETE" if missing else "SCENARIO_LINK_CHECKED",
            "missing_inputs":missing,"assumptions":link,
            "fspl_db":r.get("free_space_path_loss_db"),
            "minimum_rf_w":r.get("minimum_tx_rf_w_with_design_margin"),
            "chosen_rf_w":link.get("tx_rf_w") if link.get("tx_rf_w") is not None else r.get("minimum_tx_rf_w_with_design_margin"),
            "achieved_ebn0_db":r.get("available_ebn0_db"),
            "link_margin_db":r.get("achieved_margin_db"),
            "tx_dc_w":r.get("estimated_tx_dc_w"),
            "tx_standby_w":link.get("standby_w"),
            "tx_energy_wh":None,"tx_heat_w":r.get("estimated_dissipated_heat_w"),
            "contact_hours":contact_hours}
    if contact_hours is not None and result["tx_dc_w"] is not None:
        if contact_hours<0:raise ValueError("Invalid contact hours")
        result["tx_energy_wh"]=result["tx_dc_w"]*contact_hours
    return result
