"""Data-generation review: one code path, no silent zeros, single source of rates, interface output."""
import csv
from datetime import datetime
import json
import os
import sys
from pathlib import Path
import openpyxl
import pytest
from ttc import parameters
from ttc.subsystem_models import calculate as model_calculate, telemetry_rows
from ttc.telemetry_generation import calculate as telemetry_calculate, apply_computed_rates
from ttc.downlink_simulation import compute as simulate

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    return json.loads((ROOT / "data/telemetry_generation_inputs.json").read_text(encoding="utf-8"))


def test_both_entry_points_give_the_same_rates():
    """Regression: telemetry_generation.calculate used to let the PDF aggregate override channels."""
    cfg = inputs()
    cfg["subsystems"][2]["components"][0]["interval_seconds"] = 2   # AOCS first channel slower
    a = {r["subsystem"]: r["rate_bps"] for r in telemetry_calculate(cfg)["subsystems"]}
    b = {r["subsystem"]: r["rate_bps"] for r in telemetry_rows(cfg)}
    assert a == b and a["aocs_nominal_hk"] < 1587.2


def test_subsystem_without_inventory_or_reference_is_missing_not_zero():
    cfg = inputs()
    cfg["subsystems"].append({"name": "new_unit", "source_type": "PRELIMINARY_ESTIMATE", "source": "x", "components": []})
    rows = {r["subsystem"]: r for r in telemetry_rows(cfg)}
    assert rows["new_unit"]["rate_bps"] is None and rows["new_unit"]["validation_status"] == "MISSING_INPUT"
    result = telemetry_calculate(cfg)
    assert result["missing_subsystems"] == ["new_unit"] and result["telemetry_complete"] is False
    assert result["total_rate_bps_per_spacecraft"] == pytest.approx(2301.7422222222)  # unknown never counted as 0 bps data


def test_pdf_aggregate_is_used_when_no_channel_is_complete():
    row = telemetry_rows(inputs())[0]
    assert row["rate_bps"] == 100 and row["itemised_bps"] == 0 and row["rate_basis"] == "PDF_AGGREGATE_PROVISIONAL"


def test_pdf_aggregate_is_provisional_not_verified():
    rows = {r["subsystem"]: r for r in telemetry_rows(inputs())}
    for name in ("payload_housekeeping", "structures_mechanisms"):
        assert rows[name]["unitemised_remainder_bps"] == rows[name]["pdf_reference_bps"]
        assert rows[name]["validation_status"] == "PDF_AGGREGATE_PROVISIONAL_ITEMISATION_PENDING"
        assert rows[name]["requires_confirmation"] is True
    assert rows["aocs_nominal_hk"]["validation_status"] == "ASSUMED_INVENTORY_NO_PDF_REFERENCE"


def test_source_text_is_kept_next_to_the_basis(run_default):
    out, _ = run_default
    t = json.loads((out / "telemetry_generation.json").read_text())
    for r in t["subsystems"]:
        assert r["source"] and r["rate_basis"] and r["validation_status"]
    assert "NOT independent verification" in t["validation_warning"]
    assert t["total_unitemised_remainder_bps_per_spacecraft"] == 132


def test_traceability_csv_lists_every_channel_with_provenance(run_default):
    out, _ = run_default
    rows = list(csv.DictReader((out / "telemetry_traceability.csv").open()))
    assert {r["subsystem"] for r in rows} >= {"payload_housekeeping", "structures_mechanisms", "aocs_nominal_hk"}
    rtd = next(r for r in rows if r["channel"] == "structural_rtd")
    assert rtd["counted"] == "False" and rtd["missing_parameters"] == "bits_per_sample" and rtd["interval_provenance"] == "DOC"
    aocs = [r for r in rows if r["subsystem"] == "aocs_nominal_hk"]
    assert all(r["counted"] == "True" and r["count_provenance"] == "ASSUMPTION" for r in aocs)


def test_interface_and_per_satellite_outputs_carry_the_breakdown(run_default):
    out, _ = run_default
    iface = json.loads((out / "data_generation_interface.json").read_text())
    pay = next(r for r in iface["subsystems"] if r["subsystem"] == "payload_housekeeping")
    assert pay["itemised_bps"] == 0 and pay["unitemised_remainder_bps"] == 100 and pay["pending_real_data"] is True
    assert iface["per_spacecraft"]["unitemised_remainder_bps"] == 132
    sat = json.loads(next((out / "per_satellite").glob("*.json")).read_text())
    assert sat["telemetry_unitemised_remainder_bps"] == 132 and sat["telemetry_breakdown"]
    assert sat["obdh_buffer"]["minimum_buffer_mbit_from_peak_backlog"] == sat["downlink"]["peak_backlog_mbit"]


def test_number_of_satellites_has_a_single_source():
    assert "n_satellites" not in json.loads((ROOT / "data/subsystem_engineering_inputs.json").read_text())
    e = json.loads((ROOT / "data/subsystem_engineering_inputs.json").read_text())
    assert model_calculate(inputs(), e)["n_satellites"] == parameters.load()["n_satellites"]


def test_scenario_file_stores_no_stream_rates():
    d = json.loads((ROOT / "data/telemetry_detailed_scenario.json").read_text())
    assert all(s["rate_bps"] is None for s in d["streams"])


def test_standalone_downlink_simulation_uses_computed_not_stale_rates(tmp_path):
    old = os.getcwd(); os.chdir(ROOT)
    try:
        base = simulate(contacts_path="data/contacts_master.csv", output_dir=str(tmp_path))
    finally:
        os.chdir(old)
    g = base["satellites"]["SELENA_11"]["generated_mbit"]
    rate = telemetry_calculate(inputs())["total_rate_bps_per_spacecraft"]
    assert g == pytest.approx(rate * (  # whole input span of the contacts file
        (max(datetime.fromisoformat(r["end_utc"].replace("Z", "+00:00")) for r in csv.DictReader((ROOT / "data/contacts_master.csv").open()))
         - min(datetime.fromisoformat(r["start_utc"].replace("Z", "+00:00")) for r in csv.DictReader((ROOT / "data/contacts_master.csv").open()))).total_seconds()) / 1e6, rel=1e-6)


def run_with_inventory(tmp_path, mutate):
    from main import main
    cfg = inputs(); mutate(cfg)
    path = tmp_path / "inventory.json"; path.write_text(json.dumps(cfg))
    out = tmp_path / "out"
    old, argv = os.getcwd(), sys.argv
    os.chdir(ROOT); sys.argv = ["main.py", "--output-dir", str(out), "--telemetry-input", str(path)]
    try:
        main()
    finally:
        sys.argv = argv; os.chdir(old)
    return out


def test_changing_a_channel_interval_propagates_downstream_and_conserves_data(tmp_path, run_default):
    base_out, _ = run_default

    def slower_aocs(cfg):
        for s in cfg["subsystems"]:
            if s["name"] == "aocs_nominal_hk":
                s["components"][0]["interval_seconds"] = 1.25   # 0.625 s -> 1.25 s: half the AOCS rate
    out = run_with_inventory(tmp_path, slower_aocs)
    b, a = (json.loads((d / "telemetry_generation.json").read_text()) for d in (base_out, out))
    drop = 31 * 32 / 0.625 - 31 * 32 / 1.25
    assert b["total_rate_bps_per_spacecraft"] - a["total_rate_bps_per_spacecraft"] == pytest.approx(drop)
    pb, pa = (json.loads((d / "transfer_planning.json").read_text()) for d in (base_out, out))
    assert pb["known_total_bps"] - pa["known_total_bps"] == pytest.approx(drop)
    sb, sa = (json.loads((d / "downlink_simulation.json").read_text()) for d in (base_out, out))
    assert sa["satellites"]["SELENA_13"]["generated_mbit"] < sb["satellites"]["SELENA_13"]["generated_mbit"]
    for res in sa["satellites"].values():
        assert res["generated_mbit"] == pytest.approx(res["downloaded_mbit"] + res["remaining_mbit"], abs=1e-6)
    ia = json.loads((out / "data_generation_interface.json").read_text())
    assert ia["per_spacecraft"]["rate_bps"] == pytest.approx(a["total_rate_bps_per_spacecraft"])


def test_interface_output_for_the_link_calculations(run_default):
    out, _ = run_default
    rows = list(csv.DictReader((out / "data_generation_interface.csv").open()))
    assert [r["subsystem"] for r in rows] == [s["subsystem"] for s in json.loads((out / "telemetry_generation.json").read_text())["subsystems"]]
    for r in rows:
        assert float(r["bits_per_day"]) == pytest.approx(float(r["rate_bps"]) * 86400)
        assert r["priority"] and r["max_data_age_hours"] and r["mode"] in ("continuous", "event")
        assert r["origin"] in ("DOC", "ASSUMPTION") and r["pending_real_data"] == "True"
    j = json.loads((out / "data_generation_interface.json").read_text())
    assert j["constellation"]["rate_bps"] == pytest.approx(j["per_spacecraft"]["rate_bps"] * 8)
    assert j["constellation"]["mb_per_day"] == pytest.approx(198.870528)
    assert j["telemetry_complete"] is True and j["missing_subsystems"] == []


def test_excel_telemetry_shows_itemised_remainder_and_pending_label(run_default):
    out, _ = run_default
    ws = openpyxl.load_workbook(out / "SELENA_TTC_Model.xlsx")["Telemetry"]
    rows = {r[0]: r for r in ws.iter_rows(values_only=True) if r[0]}
    pay = rows["payload_housekeeping"]
    assert pay[8] == 100 and str(pay[9]).startswith("=") and str(pay[10]).startswith("=")
    assert "PROVISIONAL" in str(pay[13])
