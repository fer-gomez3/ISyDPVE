"""Calculate per-spacecraft telemetry (data generation) from sensor/channel inventories.

Run: python -m ttc.telemetry_generation
Rate = sum(count x bits per sample / sampling interval). A documented (PDF) aggregate is a
reference, never an override; it is the fallback only when no channel inventory exists.
A subsystem with neither is reported as MISSING_INPUT, never as zero.
Inventories marked PLACEHOLDER must be replaced by the subsystem owners' real sensor lists.
"""
import csv
import json
from pathlib import Path
from .subsystem_models import telemetry_rows, totals
from .parameters import load as load_parameters

SECONDS_PER_DAY = 86400
FIELDS = ["subsystem", "rate_bps", "mbit_per_day", "mb_per_day", "source_type", "requires_confirmation",
          "source", "rate_basis", "itemised_bps", "unitemised_remainder_bps", "itemisation_complete",
          "pdf_reference_bps", "difference_from_pdf_bps", "itemised_minus_pdf_bps", "validation_status", "owner_todo"]
TOTAL_KEYS = ("total_rate_bps_per_spacecraft", "total_itemised_bps_per_spacecraft",
              "total_unitemised_remainder_bps_per_spacecraft", "total_mbit_per_day_per_spacecraft",
              "total_mb_per_day_per_spacecraft")
TRACE_FIELDS = ["subsystem", "channel", "count", "bits_per_sample", "interval_seconds", "rate_bps", "counted",
                "count_provenance", "bits_provenance", "interval_provenance", "missing_parameters", "source", "owner_todo"]


def _public(row):
    out = {k: row[k] for k in FIELDS}
    out["components"] = row["channels"]
    out["incomplete_channels"] = row["incomplete_channels"]
    if "engineering" in row:
        out["engineering"] = row["engineering"]
    return out


def calculate(cfg):
    """Telemetry only (no engineering equations)."""
    rows = telemetry_rows(cfg)
    t = totals(rows, int(load_parameters()["n_satellites"]))
    return {"status": "PRELIMINARY_REQUIRES_SUBSYSTEM_CONFIRMATION", "scope": cfg["scope"],
            "subsystems": [_public(r) for r in rows],
            **{k: t[k] for k in TOTAL_KEYS + ("missing_subsystems", "telemetry_complete")},
            "warning": cfg["notes"]}


def apply_computed_rates(cfg, rows, set_status=False):
    """Fill stream rates from the computed telemetry rows (by name). Single source of rates."""
    by = {r["subsystem"]: r for r in rows}
    for stream in cfg["streams"]:
        row = by.get(stream["name"])
        if row is not None:
            stream["rate_bps"] = row["rate_bps"]
            if set_status:
                stream["status"] = "PDF" if row["source_type"] == "PDF" else "PRE"
    return cfg


def compute(input_path="data/telemetry_generation_inputs.json", output_dir="outputs"):
    """Calculate only telemetry data volumes for OBDH and the Earth downlink.

    IMPORTANT: EPS solar power, AOCS torques, propulsion delta-v and other hardware
    sizing equations DO NOT produce telemetry bits. Those models are optional,
    separate engineering analyses and must never control the downlink data budget.
    PDF aggregate telemetry is a provisional sizing fallback when channels are
    incomplete; it is not a derived sensor measurement.
    """
    cfg = json.loads(Path(input_path).read_text(encoding="utf-8"))
    model = calculate(cfg)
    rows = model["subsystems"]
    result = {**model,
              "n_satellites": int(load_parameters()["n_satellites"]),
              "total_mbit_per_day_constellation": model["total_mbit_per_day_per_spacecraft"] * int(load_parameters()["n_satellites"]),
              "total_mb_per_day_constellation": model["total_mb_per_day_per_spacecraft"] * int(load_parameters()["n_satellites"]),
              "validation_warning": "PDF aggregates are provisional sizing fallbacks, NOT sensor-derived rates. Hardware sizing equations do not generate telemetry; only channel count, bits/sample and sampling interval do."}
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "telemetry_generation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (out / "telemetry_generation.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({k: r[k] for k in FIELDS} for r in rows)
    with (out / "telemetry_traceability.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TRACE_FIELDS)
        writer.writeheader()
        for r in rows:
            for c in r["components"]:
                writer.writerow({"subsystem": r["subsystem"], "channel": c["name"], "count": c["count"],
                                 "bits_per_sample": c["bits_per_sample"], "interval_seconds": c["interval_seconds"],
                                 "rate_bps": c["rate_bps"], "counted": c["counted"],
                                 "count_provenance": c["provenance"]["count"],
                                 "bits_provenance": c["provenance"]["bits_per_sample"],
                                 "interval_provenance": c["provenance"]["interval_seconds"],
                                 "missing_parameters": ";".join(c["missing_parameters"]),
                                 "source": c["source"], "owner_todo": c["owner_todo"] or r["owner_todo"]})
    return result


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
