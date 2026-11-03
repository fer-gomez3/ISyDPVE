"""Formula-driven subsystem engineering and TT&C interface tests."""
import json
import math
from pathlib import Path
import pytest
from ttc.subsystem_models import calculate, channel_rate, engineering

ROOT = Path(__file__).resolve().parents[1]

def configs():
    return (json.loads((ROOT/"data/telemetry_generation_inputs.json").read_text()),
            json.loads((ROOT/"data/subsystem_engineering_inputs.json").read_text()))

def test_channel_rate_and_bad_inputs():
    assert channel_rate({"count":4,"bits_per_sample":16,"interval_seconds":10}) == 6.4
    with pytest.raises(ValueError):
        channel_rate({"count":4,"bits_per_sample":16,"interval_seconds":0})

def test_all_seven_subsystems_and_telemetry_reconcile():
    t, e = configs()
    r = calculate(t,e)
    assert len(r["subsystems"]) == 7
    assert r["n_satellites"] == 8
    assert r["total_rate_bps_per_spacecraft"] == pytest.approx(sum(s["rate_bps"] for s in r["subsystems"]))
    assert r["total_mbit_per_day_constellation"] == pytest.approx(r["total_rate_bps_per_spacecraft"]*86400*8/1e6)
    for s in r["subsystems"]:
        if s["channels"]:
            assert s["rate_bps"] == pytest.approx(sum(c["rate_bps"] for c in s["channels"]))
        assert s["engineering"]

def test_lecture_equations_are_executed():
    _, e = configs()
    eps = engineering("eps_hk",e["subsystems"]["eps_hk"])
    assert eps["p_eol_w"] < eps["p_bol_w"]
    assert eps["battery_capacity_required_wh"] > 0
    aocs = engineering("aocs_nominal_hk",e["subsystems"]["aocs_nominal_hk"])
    assert aocs["reaction_wheel_torque_requirement_nm"] >= aocs["slew_torque_nm"]
    prop = engineering("propulsion_hk",e["subsystems"]["propulsion_hk"])
    assert 0 < prop["propellant_required_kg"] < 350
    thermal = engineering("thermal_hk",e["subsystems"]["thermal_hk"])
    assert thermal["equilibrium_temperature_k"] > 0

def test_pdf_reference_is_not_silently_used_if_channels_exist():
    t, e = configs()
    t["subsystems"][0]["components"] = [{"name":"test","count":2,"bits_per_sample":16,"interval_seconds":1}]
    r = calculate(t,e)["subsystems"][0]
    assert r["rate_bps"] == 32
    assert r["pdf_reference_bps"] == 100
    assert r["difference_from_pdf_bps"] == -68
