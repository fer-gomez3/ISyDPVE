"""Regression tests for the bugs fixed in the final TT&C/OBDH version."""
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from ttc import parameters
from ttc.dsn_allocation import allocate
from ttc.downlink_simulation import run
from ttc.xband_trade_study import from_file as trade

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2030, 7, 14, tzinfo=timezone.utc)


def contact(sat, station, start_h, hours):
    s = T0 + timedelta(hours=start_h)
    return dict(id=f"{sat}-{start_h}", satellite=sat, station=station, start=s,
                end=s + timedelta(hours=hours), seconds=hours * 3600)


# ---- shared parameters -------------------------------------------------------------
def test_shared_parameters_have_a_single_source():
    shared = ("net_downlink_bps", "protocol_overhead_fraction", "setup_minutes", "min_contact_minutes",
              "daily_network_hours")
    for name in ("transfer_requirements.json", "transfer_requirements_scenario.json", "telemetry_detailed_scenario.json"):
        policy = json.loads((ROOT / "data" / name).read_text())["policy"]
        assert not [k for k in shared if k in policy], name
    dsn = json.loads((ROOT / "data/dsn_allocation_scenario.json").read_text())
    assert not [k for k in shared if k in dsn]
    assert "downlink_bps" not in json.loads((ROOT / "data/hga_preliminary_design.json").read_text())


def test_setup_is_15_minutes_and_minimum_contact_exceeds_it():
    p = parameters.load()
    assert p["dsn_setup_minutes"] == 15 and p["downlink_gross_bps"] == 256000
    assert p["min_contact_minutes"] > p["dsn_setup_minutes"]
    assert p["origins"]["dsn_setup_minutes"]["origin"] == "ASSUMPTION"
    for name in ("load_requirements",):
        from ttc.transfer_planning import load_requirements
        pol = load_requirements(str(ROOT / "data/transfer_requirements.json"))["policy"]
        assert pol["setup_minutes"] == 15 and pol["net_downlink_bps"] == 256000


def test_contact_that_cannot_carry_data_is_rejected():
    with pytest.raises(ValueError):
        allocate([contact("S1", "Madrid", 0, 2)], dict(default_fraction=1, setup_minutes=15, min_contact_minutes=15))
    bad = dict(parameters.load(), min_useful_tx_minutes=0)
    with pytest.raises(ValueError):
        parameters.validate(bad)


def test_contact_energy_optimizer_uses_the_hga_gain_not_a_second_value():
    scenario = json.loads((ROOT / "data/contact_nominal_2030_scenario.json").read_text())
    assert "tx_gain_dbi" not in scenario["link_assumptions"]
    assert parameters.hga_link_defaults()["tx_gain_dbi"] == pytest.approx(28.269, abs=1e-3)


# ---- fair DSN allocation --------------------------------------------------------------
def test_fair_allocation_serves_every_satellite_with_contacts_and_respects_the_cap():
    contacts = [contact("S1", "Madrid", 0, 4), contact("S2", "Goldstone", 0, 4), contact("S3", "Canberra", 0, 4)]
    policy = dict(default_fraction=1, setup_minutes=15, min_contact_minutes=20, daily_network_hours=1.5)
    rows = allocate(contacts, policy)
    per = {r["satellite"]: r["assigned_seconds"] for r in rows}
    assert set(per) == {"S1", "S2", "S3"} and all(v >= 20 * 60 for v in per.values())
    assert sum(per.values()) <= 1.5 * 3600 + 1e-6
    assert max(per.values()) - min(per.values()) <= 60 + 1e-6
    for r in rows:
        assert r["assigned_seconds"] <= r["geometric_candidate_seconds"] + 1e-6
        assert r["useful_tx_seconds"] == pytest.approx(max(0, r["assigned_seconds"] - 15 * 60))


def test_allocation_never_invents_contacts():
    contacts = [contact("S1", "Madrid", 0, 0.2)]  # 12 min < minimum contact
    rows = allocate(contacts, dict(default_fraction=1, setup_minutes=15, min_contact_minutes=20, daily_network_hours=3))
    assert all(not r["eligible"] and r["assigned_seconds"] == 0 for r in rows)


def test_all_eight_satellites_get_time_in_the_scenario(run_default):
    out, _ = run_default
    alloc = json.loads((out / "dsn_allocation_summary.json").read_text())
    assert len(alloc["by_satellite"]) == 8
    assert all(v["useful_hours"] > 0 for v in alloc["by_satellite"].values())
    days = {}
    for r in csv.DictReader((out / "dsn_allocated_windows.csv").open()):
        d = r["candidate_start_utc"][:10]
        days[d] = days.get(d, 0) + float(r["assigned_seconds"])
    assert max(days.values()) <= alloc["daily_network_hours_limit"] * 3600 + 1e-3


# ---- backlog simulation ---------------------------------------------------------------
def cfg_one_stream(rate=100, deadline=24):
    return {"policy": {"protocol_overhead_fraction": 0.2, "net_downlink_bps": 256000, "priority_max_age_hours": {"3": deadline}},
            "streams": [{"name": "hk", "mode": "continuous", "rate_bps": rate, "priority": 3, "max_age_hours": deadline}]}


def test_data_generated_during_a_contact_is_transmitted():
    contacts = [contact("S1", "Madrid", 2, 2), contact("S1", "Madrid", 30, 0.1)]
    policy = dict(default_fraction=1, setup_minutes=15, min_contact_minutes=20)
    r = run(cfg_one_stream(), contacts, policy)
    first = r["contacts"][0]
    assert first["backlog_after_mbit"] == pytest.approx(0, abs=1e-6)
    s = r["satellites"]["S1"]
    assert s["generated_mbit"] == pytest.approx(s["downloaded_mbit"] + s["remaining_mbit"], abs=1e-9)
    assert first["downloaded_mbit"] > 100 * (15 * 60) / 1e6  # more than just the pre-contact backlog


def test_deadline_uses_exact_age_of_the_oldest_bit():
    contacts = [contact("S1", "Madrid", 0, 0.5), contact("S1", "Madrid", 10, 1)]
    policy = dict(default_fraction=1, setup_minutes=15, min_contact_minutes=20)
    risky = run(cfg_one_stream(deadline=6), contacts, policy)["satellites"]["S1"]
    assert "hk" in risky["deadline_risk_streams"]
    assert risky["by_stream"]["hk"]["max_data_age_hours"] > 6
    ok = run(cfg_one_stream(deadline=24), contacts, policy)["satellites"]["S1"]
    assert ok["deadline_risk_streams"] == []


def test_scenario_conserves_data_and_matches_an_independent_aggregate_model(run_default):
    out, _ = run_default
    sim = json.loads((out / "downlink_simulation.json").read_text())
    eff = sim["effective_data_bps"]
    g = sum(r["rate_bps"] for r in json.loads((out / "telemetry_generation.json").read_text())["subsystems"])
    rows = list(csv.DictReader((out / "dsn_allocated_windows.csv").open()))
    start = min(datetime.fromisoformat(c["start_utc"]) for c in sim["contacts"])
    for sat, res in sim["satellites"].items():
        assert res["generated_mbit"] == pytest.approx(res["downloaded_mbit"] + res["remaining_mbit"], abs=1e-6)
        wins = sorted((w for w in rows if w["satellite"] == sat and float(w["useful_tx_seconds"]) > 0), key=lambda w: w["candidate_start_utc"])
        t, b, sent = None, 0.0, 0.0
        t0 = datetime.fromisoformat(min(w["candidate_start_utc"] for w in rows))
        horizon = res["generated_mbit"] * 1e6 / g
        t = 0.0
        for w in wins:
            a = (datetime.fromisoformat(w["candidate_start_utc"]) - t0).total_seconds() + 15 * 60
            use = float(w["useful_tx_seconds"])
            b += g * max(0.0, a - t); t = a
            if eff > g:
                clear = b / (eff - g)
                if clear <= use:
                    sent += b + g * use; b = 0.0
                else:
                    sent += eff * use; b = b + g * use - eff * use
            else:
                sent += eff * use; b = max(0.0, b + g * use - eff * use)
            t = a + use
        b += g * max(0.0, horizon - t)
        assert res["downloaded_mbit"] == pytest.approx(sent / 1e6, abs=0.1 * max(1, len(wins)))


# ---- connections between modules ----------------------------------------------------------
def test_xband_study_includes_the_hga_baseline_gain(run_default):
    out, _ = run_default
    result = json.loads((out / "xband_trade_study.json").read_text())
    gains = {round(c["inputs"]["tx_gain_dbi"], 2) for c in result["cases"]}
    assert 28.27 in gains and result["case_count"] == 216
    assert trade()["case_count"] == 180


def test_eight_satellite_outputs_exist(run_default):
    out, _ = run_default
    files = sorted((out / "per_satellite").glob("SELENA_*.json"))
    assert len(files) == 8
    rec = json.loads(files[0].read_text())
    assert rec["status"].startswith("HYPOTHETICAL") and rec["downlink"]["generated_mbit"] > 0
    rows = list(csv.DictReader((out / "per_satellite_summary.csv").open()))
    assert len(rows) == 8


def test_all_transfer_streams_resolve_to_a_generated_rate(run_default):
    out, _ = run_default
    planning = json.loads((out / "transfer_planning.json").read_text())
    assert planning["missing"] == [] and planning["telemetry_complete"]
    assert planning["contacts"] and all(c["scenario_capacity_mbit"] is not None for c in planning["contacts"])
