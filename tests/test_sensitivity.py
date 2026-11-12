"""Input changes must propagate through the relevant modules and into the Excel workbook."""
import json
import math
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
import openpyxl
import pytest
from ttc.hga_sizing import calculate as hga_calc
from ttc.link_budget import evaluate_link
from ttc.telemetry_generation import calculate as telemetry
from ttc.downlink_simulation import run

ROOT = Path(__file__).resolve().parents[1]
LINK = dict(distance_km=400000, rx_gt_db_per_k=30, required_ebn0_db=10, losses_db=3, margin_db=3)


def load(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


def test_sensor_count_changes_the_telemetry_budget_exactly():
    cfg = load("telemetry_generation_inputs.json")
    base = telemetry(cfg)["total_rate_bps_per_spacecraft"]
    for s in cfg["subsystems"]:
        if s["name"] == "aocs_nominal_hk":
            s["components"][0]["count"] = 62
    assert telemetry(cfg)["total_rate_bps_per_spacecraft"] - base == pytest.approx(31 * 32 / 0.625)


def test_antenna_diameter_changes_gain_and_required_rf_power():
    ant, link = load("hga_preliminary_design.json"), dict(LINK, data_rate_bps=256000)
    a = hga_calc(ant, link)
    big = hga_calc({**ant, "diameter_m": 0.60}, link)
    dg = big["calculated_idealized_gain_dbi"] - a["calculated_idealized_gain_dbi"]
    assert dg == pytest.approx(20 * math.log10(0.60 / 0.38))
    ratio = big["link"]["minimum_tx_rf_w_with_design_margin"] / a["link"]["minimum_tx_rf_w_with_design_margin"]
    assert ratio == pytest.approx(10 ** (-dg / 10))


def test_transmit_power_and_data_rate_change_margin_and_rf():
    base = dict(LINK, frequency_hz=8.4e9, tx_gain_dbi=28.27, data_rate_bps=256000)
    pmin = evaluate_link(base)["minimum_tx_rf_w_with_design_margin"]
    for factor in (0.5, 1, 2):
        r = evaluate_link({**base, "tx_rf_w": pmin * factor})
        assert r["achieved_margin_db"] == pytest.approx(3 + 10 * math.log10(factor), abs=1e-9)
    half = evaluate_link({**base, "data_rate_bps": 128000})["minimum_tx_rf_w_with_design_margin"]
    assert half == pytest.approx(pmin / 2)


def test_downlink_rate_changes_capacity_and_limits_the_download_when_binding():
    t0 = datetime(2030, 7, 14, tzinfo=timezone.utc)
    contacts = [dict(id="a", satellite="S1", station="Madrid", start=t0, end=t0 + timedelta(hours=1), seconds=3600)]
    policy = dict(default_fraction=1, setup_minutes=15, min_contact_minutes=20)

    def cfg(rate, stream_bps):
        return {"policy": {"protocol_overhead_fraction": 0.2, "net_downlink_bps": rate, "priority_max_age_hours": {"3": 24}},
                "streams": [{"name": "x", "mode": "continuous", "rate_bps": stream_bps, "priority": 3, "max_age_hours": 24}]}
    fast, slow = run(cfg(256000, 100), contacts, policy), run(cfg(128000, 100), contacts, policy)
    assert slow["effective_data_bps"] == fast["effective_data_bps"] / 2
    assert slow["contacts"][0]["capacity_mbit"] == pytest.approx(fast["contacts"][0]["capacity_mbit"] / 2)
    assert slow["contacts"][0]["downloaded_mbit"] == pytest.approx(fast["contacts"][0]["downloaded_mbit"])
    # a stream faster than the link: the download is capacity limited and halves with the rate
    f2, s2 = run(cfg(256000, 400000), contacts, policy), run(cfg(128000, 400000), contacts, policy)
    assert s2["contacts"][0]["downloaded_mbit"] == pytest.approx(f2["contacts"][0]["downloaded_mbit"] / 2, rel=1e-6)


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice not installed")
def test_excel_recalculates_after_input_changes(run_linked, tmp_path):
    out, _ = run_linked
    wb = openpyxl.load_workbook(out / "SELENA_TTC_Model.xlsx")
    rows = {r[0].value: r[0].row for r in wb["Inputs"].iter_rows(min_row=2) if r[0].value}
    wb.save(tmp_path / "base.xlsx")
    wb["Inputs"].cell(rows["hga_d_m"], 3).value = 0.60
    wb["Inputs"].cell(rows["rate_bps"], 3).value = 128000
    for r in wb["Telemetry"].iter_rows(min_row=2):
        if r[0].value == "aocs_nominal_hk" and r[2].value == 31:
            r[2].value = 62
    wb.save(tmp_path / "mod.xlsx")
    subprocess.run(["soffice", "--headless", "--convert-to", "xlsx", "--outdir", str(tmp_path / "out"),
                    str(tmp_path / "base.xlsx"), str(tmp_path / "mod.xlsx")], check=True, capture_output=True, timeout=180)

    def values(name):
        v = openpyxl.load_workbook(tmp_path / "out" / name, data_only=True)
        d = {f"{ws}:{r[0]}": r[1] for ws in ("Link", "Capacity", "HGA", "Power") for r in v[ws].iter_rows(min_row=2, values_only=True) if r[0]}
        d["tel"] = next(r[5] for r in v["Telemetry"].iter_rows(values_only=True) if r[0] == "TOTAL per satellite")
        d["checks"] = [r[4] for r in v["Checks"].iter_rows(min_row=2, values_only=True)]
        errors = [c.value for ws in v for row in ws.iter_rows() for c in row if isinstance(c.value, str) and c.value.startswith(("#", "Err:"))]
        assert not errors
        return d
    a, b = values("base.xlsx"), values("mod.xlsx")
    assert "DIFF" not in a["checks"] and a["checks"].count("OK") >= 3
    assert b["tel"] - a["tel"] == pytest.approx(31 * 32 / 0.625)
    dg = 20 * math.log10(0.60 / 0.38)
    assert b["HGA:Idealized gain"] - a["HGA:Idealized gain"] == pytest.approx(dg)
    expected = 10 ** ((-dg + 10 * math.log10(128000 / 256000)) / 10)
    assert b["Link:Minimum RF power incl. margin"] / a["Link:Minimum RF power incl. margin"] == pytest.approx(expected)
    assert b["Capacity:Net data rate after protocol overhead"] == pytest.approx(102400)
    assert b["Power:Transmitter DC power"] < a["Power:Transmitter DC power"]
