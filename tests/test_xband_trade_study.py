"""Basic regression tests for SELENA X-band parametric calculations."""
from ttc.xband_trade_study import from_file

def test_scenario_case_count():
    result=from_file()
    assert result["case_count"]==180
    assert result["status"]=="ASSUMPTIONS_NOT_VERIFIED"
    assert len(result["missing_verified_inputs"])==3

def test_power_decreases_with_gain():
    cases=from_file()["cases"]
    a=next(x for x in cases if x["inputs"]["distance_km"]==400000 and x["inputs"]["rx_gt_db_per_k"]==30 and x["inputs"]["data_rate_bps"]==256000 and x["inputs"]["tx_gain_dbi"]==20)
    b=next(x for x in cases if x["inputs"]["distance_km"]==400000 and x["inputs"]["rx_gt_db_per_k"]==30 and x["inputs"]["data_rate_bps"]==256000 and x["inputs"]["tx_gain_dbi"]==33)
    assert a["minimum_tx_rf_w_with_design_margin"]>b["minimum_tx_rf_w_with_design_margin"]
