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
          "source", "telemetry_origin", "pdf_reference_bps", "difference_from_pdf_bps", "validation_status"]


def _public(row):
    out = {k: row[k] for k in FIELDS}
    out["components"] = row["channels"]
    if "engineering" in row:
        out["engineering"] = row["engineering"]
    return out


def calculate(cfg):
    """Telemetry only (no engineering equations)."""
    rows = telemetry_rows(cfg)
    t = totals(rows, int(load_parameters()["n_satellites"]))
    return {"status": "PRELIMINARY_REQUIRES_SUBSYSTEM_CONFIRMATION", "scope": cfg["scope"],
            "subsystems": [_public(r) for r in rows],
            **{k: t[k] for k in ("total_rate_bps_per_spacecraft", "total_mbit_per_day_per_spacecraft",
                                 "total_mb_per_day_per_spacecraft", "missing_subsystems", "telemetry_complete")},
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
    """Calculate subsystem engineering first, then feed computed rates to TT&C."""
    from .subsystem_models import compute as compute_subsystems
    model = compute_subsystems(telemetry_path=input_path, output_dir=output_dir)
    rows = [_public(r) for r in model["subsystems"]]
    result = {"status": model["status"], "scope": model["scope"], "subsystems": rows,
              **{k: model[k] for k in ("total_rate_bps_per_spacecraft", "total_mbit_per_day_per_spacecraft",
                                       "total_mb_per_day_per_spacecraft", "total_mbit_per_day_constellation",
                                       "total_mb_per_day_constellation", "n_satellites", "missing_subsystems",
                                       "telemetry_complete")},
              "validation_warning": model["validation_warning"], "warning": model["warning"]}
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "telemetry_generation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (out / "telemetry_generation.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({k: r[k] for k in FIELDS} for r in rows)
    return result


if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
