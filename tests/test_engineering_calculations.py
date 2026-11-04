import pytest
from ttc.engineering_calculations import calculate

def test_known_data_is_not_mistaken_for_complete_total():
    r = calculate()
    assert r["known_daily_mbit"] == pytest.approx(11.4048)
    assert r["total_daily_mbit"] is None
    assert "eps" in r["missing_rates"]
    assert r["minimum_downlink_bps_for_all_data"] is None

def test_example_30min_contact():
    r = calculate(contact_seconds=1800)
    assert r["minimum_downlink_bps_for_known_data"] == pytest.approx(6336.0)

def test_overhead():
    r = calculate(contact_seconds=1800, overhead_fraction=0.2)
    assert r["minimum_downlink_bps_for_known_data"] == pytest.approx(7920.0)

def test_all_rates_provided():
    missing = ["aocs", "eps", "thermal", "propulsion", "obdh"]
    r = calculate(other_rates_bps={k: 0.0 for k in missing})
    assert r["total_daily_mbit"] == pytest.approx(11.4048)
    assert r["data_completeness"] == "complete"

def test_invalid_contact():
    with pytest.raises(ValueError):
        calculate(contact_seconds=0)
