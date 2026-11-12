"""Opt-in reverse-engineering scenario: preserve baseline and trace calibration assumptions."""
import json
from pathlib import Path
import pytest
from ttc.subsystem_models import telemetry_rows

ROOT = Path(__file__).resolve().parents[1]


def test_reverse_engineering_is_opt_in_and_reproduces_pdf():
    baseline = json.loads((ROOT / "data/telemetry_generation_inputs.json").read_text())
    scenario = json.loads((ROOT / "data/telemetry_reverse_engineered_scenario.json").read_text())
    base = {r["subsystem"]: r for r in telemetry_rows(baseline)}
    rows = {r["subsystem"]: r for r in telemetry_rows(scenario)}
    for name, target in (("payload_housekeeping", 100), ("structures_mechanisms", 32)):
        assert base[name]["rate_basis"] == "PDF_AGGREGATE_PROVISIONAL"
        assert rows[name]["rate_bps"] == pytest.approx(target)
        assert rows[name]["itemised_bps"] == pytest.approx(target)
        assert rows[name]["unitemised_remainder_bps"] == pytest.approx(0)
        assert rows[name]["pdf_reference_bps"] == target
        assert rows[name]["requires_confirmation"]
        assert any("ASSUMPTION" in c["provenance"].values() for c in rows[name]["channels"])


def test_reverse_engineering_sensitivity_does_not_force_pdf_match():
    cfg = json.loads((ROOT / "data/telemetry_reverse_engineered_scenario.json").read_text())
    payload = next(s for s in cfg["subsystems"] if s["name"] == "payload_housekeeping")
    payload["components"][0]["interval_seconds"] = 2
    row = next(r for r in telemetry_rows(cfg) if r["subsystem"] == "payload_housekeeping")
    assert row["rate_bps"] == pytest.approx(96)
    assert row["difference_from_pdf_bps"] == pytest.approx(-4)
    assert row["requires_confirmation"]


def test_documented_structure_values_preserved():
    cfg = json.loads((ROOT / "data/telemetry_reverse_engineered_scenario.json").read_text())
    row = next(r for r in telemetry_rows(cfg) if r["subsystem"] == "structures_mechanisms")
    ch = {c["name"]: c for c in row["channels"]}
    assert ch["sadm_encoder"]["provenance"]["count"] == "DOC"
    assert ch["sadm_encoder"]["provenance"]["interval_seconds"] == "ASSUMPTION"
    assert ch["structural_rtd"]["provenance"]["interval_seconds"] == "DOC"
    assert ch["structural_rtd"]["provenance"]["bits_per_sample"] == "ASSUMPTION"
