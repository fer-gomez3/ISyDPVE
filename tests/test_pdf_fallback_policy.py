"""Acceptance tests for the approved PDF fallback / owner-data transition."""
import json
from pathlib import Path
import pytest
from ttc.subsystem_models import telemetry_rows

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    return json.loads((ROOT / "data/telemetry_generation_inputs.json").read_text())


def by_name(cfg, name):
    return next(r for r in telemetry_rows(cfg) if r["subsystem"] == name)


@pytest.mark.parametrize("name,reference", [
    ("payload_housekeeping", 100),
    ("structures_mechanisms", 32),
])
def test_pdf_fallback_keeps_unknowns_and_documents_formula(name, reference):
    cfg = inputs()
    source = next(s for s in cfg["subsystems"] if s["name"] == name)
    row = by_name(cfg, name)
    assert source["pdf_rate_bps"] == reference
    assert "bits_per_sample_i / interval_seconds_i" in source["telemetry_formula"]
    assert "components[].interval_seconds" in source["required_variables"]
    assert row["rate_bps"] == reference
    assert row["rate_basis"] == "PDF_AGGREGATE_PROVISIONAL"
    assert row["requires_confirmation"]
    assert any(not c["counted"] for c in row["channels"])


def test_partial_owner_data_preserves_fallback_and_exposes_remainder():
    cfg = inputs()
    payload = cfg["subsystems"][0]
    payload["components"][0].update(count=1, bits_per_sample=16, interval_seconds=2, provenance="OWNER")
    row = by_name(cfg, "payload_housekeeping")
    assert row["itemised_bps"] == pytest.approx(8)
    assert row["unitemised_remainder_bps"] == pytest.approx(92)
    assert row["rate_bps"] == pytest.approx(100)


def test_complete_owner_inventory_overrides_pdf_and_reports_difference():
    cfg = inputs()
    payload = cfg["subsystems"][0]
    payload["components"] = [
        {"name": "owner_verified_channel", "count": 5, "bits_per_sample": 16,
         "interval_seconds": 1, "provenance": "OWNER"}
    ]
    payload["itemisation_complete"] = True
    row = by_name(cfg, "payload_housekeeping")
    assert row["rate_bps"] == pytest.approx(80)
    assert row["itemised_bps"] == pytest.approx(80)
    assert row["difference_from_pdf_bps"] == pytest.approx(-20)
    assert row["rate_basis"] == "CHANNELS_ITEMISATION_COMPLETE"
    assert not row["requires_confirmation"]
