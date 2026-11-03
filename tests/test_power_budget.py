import math
import pytest
from ttc.power_budget import evaluate

BASE=dict(distance_km=384400,frequency_hz=8.4e9,tx_gain_dbi=30,
          rx_gt_db_per_k=50,data_rate_bps=2000,required_ebn0_db=10,
          losses_db=3,margin_db=3,pa_efficiency=0.4,electronics_w=5,
          standby_w=2)

def test_unknowns_remain_unknown():
    x=evaluate({"distance_km":None})
    assert x["status"]=="INCOMPLETE"
    assert x["tx_dc_w"] is None

def test_rf_electrical_and_thermal_consistency():
    sized=evaluate(BASE,contact_hours=2)
    assert sized["minimum_rf_w"]>0
    x=evaluate({**BASE,"tx_rf_w":sized["minimum_rf_w"]},contact_hours=2)
    assert math.isclose(x["link_margin_db"],3,abs_tol=1e-9)
    assert math.isclose(x["tx_dc_w"],x["chosen_rf_w"]/0.4+5)
    assert math.isclose(x["tx_heat_w"],x["tx_dc_w"]-x["chosen_rf_w"])
    assert math.isclose(x["tx_energy_wh"],2*x["tx_dc_w"])

def test_invalid_efficiency():
    with pytest.raises(ValueError):
        evaluate({**BASE,"pa_efficiency":0})
