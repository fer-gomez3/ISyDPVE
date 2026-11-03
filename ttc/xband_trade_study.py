"""SELENA parametric X-band study. Results are not validated hardware specifications."""
import json
from pathlib import Path
from ttc.link_budget import evaluate_link

def calculate(cfg, extra_gains_dbi=()):
    """extra_gains_dbi: additional antenna gain cases, e.g. the calculated gain of the HGA baseline."""
    b=cfg["baseline"]
    missing=[key for key,value in {
        "antenna gain":cfg["antenna"]["guaranteed_gain_dbi"],
        "DSN G/T":cfg["ground_station"]["verified_gt_db_per_k"],
        "coding Eb/N0":cfg["coding"]["verified_required_ebn0_db"]
    }.items() if value is None]
    cases=[]
    for distance in cfg["distance_cases_km"]:
        for gt in cfg["ground_gt_cases_db_per_k"]:
            for gain in [*cfg["antenna_gain_cases_dbi"],*extra_gains_dbi]:
                for rate in cfg["data_rate_cases_bps"]:
                    p=dict(distance_km=distance,frequency_hz=b["frequency_hz"],
                           tx_gain_dbi=gain,rx_gt_db_per_k=gt,data_rate_bps=rate,
                           required_ebn0_db=b["assumed_required_ebn0_db"],
                           losses_db=sum(cfg["losses_db"].values()),
                           margin_db=b["design_margin_db"],
                           pa_efficiency=b["assumed_pa_efficiency"],
                           electronics_w=b["assumed_electronics_w"])
                    result=evaluate_link(p)
                    result["inputs"]=p
                    result["dc_with_pointing_w"]=result["estimated_tx_dc_w"]+b["assumed_antenna_pointing_w"]
                    cases.append(result)
    return dict(status="ASSUMPTIONS_NOT_VERIFIED" if missing else "INPUTS_VERIFIED",
                missing_verified_inputs=missing,case_count=len(cases),
                cases=cases,notes=cfg["notes"])

def from_file(path="data/selena_xband_trade_scenario.json", extra_gains_dbi=()):
    return calculate(json.loads(Path(path).read_text(encoding="utf-8")),extra_gains_dbi)

if __name__=="__main__":
    result=from_file()
    out=Path("outputs/xband_trade_study.json")
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(result["status"],result["case_count"],"cases")
