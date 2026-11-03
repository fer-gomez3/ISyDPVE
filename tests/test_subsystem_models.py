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
        assert s["itemised_bps"] == pytest.approx(sum(c["rate_bps"] for c in s["channels"] if c["counted"]))
        assert s["engineering"]

def test_lecture_equations_are_executed():
    _, e = configs()
    eps = engineering("eps_hk",e["subsystems"]["eps_hk"])
    assert eps["p_eol_w_m2"] < eps["p_bol_w_m2"]
    assert eps["battery_capacity_required_wh"] > 0
    aocs = engineering("aocs_nominal_hk",e["subsystems"]["aocs_nominal_hk"])
    assert aocs["reaction_wheel_torque_requirement_nm"] >= aocs["slew_torque_nm"]
    prop = engineering("propulsion_hk",e["subsystems"]["propulsion_hk"])
    assert 0 < prop["propellant_required_kg"] < 350
    thermal = engineering("thermal_hk",e["subsystems"]["thermal_hk"])
    assert thermal["equilibrium_temperature_k"] > 0

def _row(cfg, name):
    return {r["subsystem"]: r for r in calculate(cfg, configs()[1])["subsystems"]}[name]


def test_reverse_engineered_pdf_targets_are_calculated_and_unverified():
    t, e = configs()
    rows = {r["subsystem"]: r for r in calculate(t, e)["subsystems"]}
    for name, reference in (("payload_housekeeping", 100), ("structures_mechanisms", 32)):
        row = rows[name]
        assert row["rate_bps"] == pytest.approx(reference)
        assert row["itemised_bps"] == pytest.approx(reference)
        assert row["unitemised_remainder_bps"] == pytest.approx(0)
        assert row["rate_basis"] == "REVERSE_ENGINEERED_ESTIMATE"
        assert row["validation_status"] == "REVERSE_ENGINEERED_MATCH_UNVERIFIED"
        assert row["requires_confirmation"]
        assert all(c["counted"] for c in row["channels"])
    p = next(s for s in t["subsystems"] if s["name"] == "payload_housekeeping")
    p["components"][0]["interval_seconds"] = 2
    altered = {r["subsystem"]: r for r in calculate(t, e)["subsystems"]}
    assert altered["payload_housekeeping"]["rate_bps"] == pytest.approx(96)
    assert altered["payload_housekeeping"]["difference_from_pdf_bps"] == pytest.approx(-4)
    assert altered["payload_housekeeping"]["validation_status"] == "REVERSE_ENGINEERED_DIFFERS_FROM_PDF"


def test_structures_preserves_pdf_provenance_and_inferred_parameters():
    t, _ = configs()
    ch = {c["name"]: c for c in _row(t, "structures_mechanisms")["channels"]}
    assert ch["sadm_encoder"]["provenance"]["count"] == "DOC"
    assert ch["sadm_encoder"]["provenance"]["interval_seconds"] == "ASSUMPTION"
    assert ch["structural_rtd"]["provenance"]["interval_seconds"] == "DOC"
    assert ch["structural_rtd"]["provenance"]["bits_per_sample"] == "ASSUMPTION"


def test_totals_stay_consistent():
    t, e = configs()
    r = calculate(t, e)
    assert r["total_rate_bps_per_spacecraft"] == pytest.approx(2301.742222222)
    assert r["total_unitemised_remainder_bps_per_spacecraft"] == pytest.approx(0)
    assert r["total_itemised_bps_per_spacecraft"] == pytest.approx(r["total_rate_bps_per_spacecraft"])


def test_eps_single_methodology_and_pdf_differences_visible():
    _, e = configs()
    p = e["subsystems"]["eps_hk"]
    out = engineering("eps_hk", p)
    assert "eol_specific_power_w_m2" not in p and "cell_power_w" not in p
    assert out["solar_area_m2"] == pytest.approx(out["required_solar_power_w"] / out["p_eol_w_m2"])
    assert out["pdf_reference"]["array_eol_w"] == 410
    assert out["pdf_reference"]["required_solar_power_minus_pdf_array_w"] == pytest.approx(out["required_solar_power_w"] - 410)
    assert out["pdf_reference"]["battery_capacity_minus_pdf_wh"] == pytest.approx(out["battery_capacity_required_wh"] - 1800)
    assert out["pdf_reference"]["pdf_solar_area_m2"] is None


def test_aocs_uses_variable_radius_and_sums_torques():
    _, e = configs()
    p = dict(e["subsystems"]["aocs_nominal_hk"])
    base = engineering("aocs_nominal_hk", p)
    assert base["radius_basis"] == "CIRCULAR_RADIUS_LOWER_BOUND_PERIAPSIS_INPUT_NEEDED"
    p.update(periapsis_radius_m=2.0e6, apoapsis_radius_m=6.2e6)
    out = engineering("aocs_nominal_hk", p)
    assert out["radius_basis"] == "PERIAPSIS_RADIUS"
    assert out["gravity_gradient_torque_nm"] == pytest.approx(out["gravity_gradient_torque_periapsis_nm"])
    assert out["gravity_gradient_torque_periapsis_nm"] / out["gravity_gradient_torque_apoapsis_nm"] == pytest.approx((6.2e6 / 2.0e6) ** 3)
    a, ecc = out["semi_major_axis_m"], out["eccentricity"]
    assert a == pytest.approx(4.1e6) and ecc == pytest.approx(4.2e6 / 8.2e6)
    k = out["gravity_gradient_torque_periapsis_nm"] * 2.0e6 ** 3
    assert out["gravity_gradient_torque_orbit_average_nm"] == pytest.approx(k * a ** -3 * (1 - ecc ** 2) ** -1.5)
    assert (out["gravity_gradient_torque_apoapsis_nm"] < out["gravity_gradient_torque_orbit_average_nm"]
            < out["gravity_gradient_torque_periapsis_nm"])
    margin = p["torque_margin_factor"]
    assert out["reaction_wheel_torque_requirement_nm"] == pytest.approx(
        (out["slew_torque_nm"] + out["gravity_gradient_torque_nm"]) * margin)
    assert out["reaction_wheel_torque_requirement_nm"] >= out["reaction_wheel_torque_max_only_nm"]
