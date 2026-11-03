"""Data-generation interface for the satellite-to-Earth link calculations.

One row per subsystem (per spacecraft): generated rate, daily volume, how soon the data must
reach Earth (priority, maximum data age) and how trustworthy the number is. Totals are given
per spacecraft and for the constellation. Rates are never padded or forced to documentation
values; missing inputs stay empty.
"""
import csv
import json
from pathlib import Path

ORIGIN = {"PDF": "DOC", "PRELIMINARY_ESTIMATE": "ASSUMPTION", "MISSING_INPUT": "INPUT NEEDED"}
FIELDS = ["subsystem", "rate_bps", "bits_per_day", "mbit_per_day", "mb_per_day", "mode", "priority",
          "max_data_age_hours", "min_transfers_per_day", "origin", "pending_real_data",
          "rate_basis", "itemised_bps", "unitemised_remainder_bps", "itemisation_complete",
          "pdf_reference_bps", "difference_from_pdf_bps", "validation_status", "source", "owner_todo"]


def build(telemetry, streams, modes=None):
    modes = modes or {}
    by_stream = {s["name"]: s for s in streams}
    rows = []
    for r in telemetry["subsystems"]:
        s = by_stream.get(r["subsystem"], {})
        rate = r["rate_bps"]
        rows.append({
            "subsystem": r["subsystem"], "rate_bps": rate,
            "bits_per_day": None if rate is None else rate * 86400,
            "mbit_per_day": r["mbit_per_day"], "mb_per_day": r["mb_per_day"],
            "mode": modes.get(r["subsystem"]), "priority": s.get("priority"),
            "max_data_age_hours": s.get("deadline_hours"),
            "min_transfers_per_day": None if not s.get("deadline_hours") else 24 / s["deadline_hours"],
            "origin": ORIGIN[r["source_type"]], "pending_real_data": r["requires_confirmation"],
            "rate_basis": r["rate_basis"], "itemised_bps": r["itemised_bps"],
            "unitemised_remainder_bps": r["unitemised_remainder_bps"], "itemisation_complete": r["itemisation_complete"],
            "pdf_reference_bps": r["pdf_reference_bps"], "difference_from_pdf_bps": r["difference_from_pdf_bps"],
            "validation_status": r["validation_status"], "source": r["source"], "owner_todo": r["owner_todo"]})
    return rows


def write(telemetry, streams, out_dir="outputs", modes=None):
    out = Path(out_dir)
    rows = build(telemetry, streams, modes)
    with (out / "data_generation_interface.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    summary = {"status": telemetry["status"], "scope": telemetry["scope"],
               "per_spacecraft": {"rate_bps": telemetry["total_rate_bps_per_spacecraft"],
                                  "mbit_per_day": telemetry["total_mbit_per_day_per_spacecraft"],
                                  "mb_per_day": telemetry["total_mb_per_day_per_spacecraft"],
                                  "itemised_bps": telemetry["total_itemised_bps_per_spacecraft"],
                                  "unitemised_remainder_bps": telemetry["total_unitemised_remainder_bps_per_spacecraft"]},
               "constellation": {"n_satellites": telemetry["n_satellites"],
                                 "rate_bps": telemetry["total_rate_bps_per_spacecraft"] * telemetry["n_satellites"],
                                 "mbit_per_day": telemetry["total_mbit_per_day_constellation"],
                                 "mb_per_day": telemetry["total_mb_per_day_constellation"]},
               "telemetry_complete": telemetry["telemetry_complete"],
               "missing_subsystems": telemetry["missing_subsystems"],
               "validation_warning": telemetry["validation_warning"],
               "subsystems": rows}
    (out / "data_generation_interface.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary
