"""Unit checks for preliminary link budget (pytest)."""
import math
import pytest
from ttc.link_budget import evaluate_link

BASE=dict(distance_km=384400,frequency_hz=8.4e9,tx_gain_dbi=30,
          rx_gt_db_per_k=50,data_rate_bps=256000,
          required_ebn0_db=10,losses_db=3,margin_db=3,
          tx_rf_w=None,pa_efficiency=0.4,electronics_w=5)

def test_missing_inputs():
    result=evaluate_link({"distance_km":384400})
    assert result["status"]=="MISSING_INPUTS"
    assert "frequency_hz" in result["missing_inputs"]

def test_link_math_and_power():
    r=evaluate_link(BASE)
    assert 220<r["free_space_path_loss_db"]<225
    assert r["minimum_tx_rf_w_with_design_margin"]>0
    assert r["estimated_tx_dc_w"]>r["minimum_tx_rf_w_with_design_margin"]
    assert r["estimated_dissipated_heat_w"]>0

def test_rate_doubling_requires_3db_more_eirp():
    p=dict(BASE);p["data_rate_bps"]*=2
    a=evaluate_link(BASE);b=evaluate_link(p)
    assert b["required_eirp_dbw"]-a["required_eirp_dbw"]==pytest.approx(10*math.log10(2))

def test_actual_power_margin():
    p=dict(BASE);p["tx_rf_w"]=evaluate_link(BASE)["minimum_tx_rf_w_with_design_margin"]
    r=evaluate_link(p)
    assert r["achieved_margin_db"]==pytest.approx(BASE["margin_db"])

def test_invalid_inputs():
    p=dict(BASE);p["pa_efficiency"]=0
    with pytest.raises(ValueError):evaluate_link(p)
