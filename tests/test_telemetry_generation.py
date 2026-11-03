"""Regression checks for PDF and preliminary telemetry, including event streams."""
import json
from pathlib import Path
import pytest
from ttc.telemetry_generation import calculate
from ttc.transfer_planning import stream_rate, stream_requirements

ROOT=Path(__file__).resolve().parents[1]

def test_telemetry_totals_and_provenance():
    cfg=json.loads((ROOT/"data/telemetry_generation_inputs.json").read_text(encoding="utf-8"))
    result=calculate(cfg)
    rates={r["subsystem"]:r for r in result["subsystems"]}
    assert rates["payload_housekeeping"]["rate_bps"]==100
    assert rates["structures_mechanisms"]["rate_bps"]==32
    assert rates["aocs_nominal_hk"]["requires_confirmation"] is True
    assert result["total_rate_bps_per_spacecraft"]==pytest.approx(2301.7422222222)
    assert result["total_mb_per_day_per_spacecraft"]==pytest.approx(24.858816)

def test_event_average_rate_fallback():
    assert stream_rate({"mode":"event","rate_bps":38.4,"bytes_per_event":None,"event_interval_hours":None})==38.4
    assert stream_rate({"mode":"event","bytes_per_event":3600,"event_interval_hours":2})==4.0
    with pytest.raises(ValueError):
        stream_rate({"mode":"event","bytes_per_event":100,"event_interval_hours":0})

def test_generated_rates_resolve_all_planning_streams():
    cfg=json.loads((ROOT/"data/telemetry_generation_inputs.json").read_text(encoding="utf-8"))
    calculated={r["subsystem"]:r["rate_bps"] for r in calculate(cfg)["subsystems"]}
    planning=json.loads((ROOT/"data/transfer_requirements.json").read_text(encoding="utf-8"))
    for s in planning["streams"]:
        if s["name"] in calculated:
            s["rate_bps"]=calculated[s["name"]]
    streams=stream_requirements(planning)
    assert all(s["mean_rate_bps"] is not None for s in streams)
    assert sum(s["mean_rate_bps"] for s in streams)==pytest.approx(2301.7422222222)
