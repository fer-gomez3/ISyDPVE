"""Calculate per-spacecraft telemetry from PDF aggregate rates or editable sensor assumptions.

Run: python -m ttc.telemetry_generation
PDF aggregate rates take precedence. Preliminary channels are hypothetical.
"""
import csv
import json
from pathlib import Path

SECONDS_PER_DAY = 86400

def calculate(cfg):
    rows = []
    for subsystem in cfg["subsystems"]:
        parts = []
        for c in subsystem.get("components", []):
            n, bits, period = int(c["count"]), float(c["bits_per_sample"]), float(c["interval_seconds"])
            if n < 0 or bits < 0 or period <= 0:
                raise ValueError("Invalid telemetry component: " + str(c))
            parts.append({"name": c["name"], "count": n, "bits_per_sample": bits,
                          "interval_seconds": period, "rate_bps": n * bits / period})
        pdf_rate = subsystem.get("pdf_rate_bps")
        rate = float(pdf_rate) if pdf_rate is not None else sum(p["rate_bps"] for p in parts)
        if rate < 0:
            raise ValueError("Negative telemetry rate")
        rows.append({"subsystem": subsystem["name"], "rate_bps": rate,
                     "mbit_per_day": rate * SECONDS_PER_DAY / 1e6,
                     "mb_per_day": rate * SECONDS_PER_DAY / 8e6,
                     "source_type": subsystem["source_type"], "source": subsystem["source"],
                     "requires_confirmation": subsystem["source_type"] != "PDF",
                     "components": parts})
    total = sum(r["rate_bps"] for r in rows)
    return {"status": "PRELIMINARY_REQUIRES_SUBSYSTEM_CONFIRMATION",
            "scope": cfg["scope"], "subsystems": rows,
            "total_rate_bps_per_spacecraft": total,
            "total_mbit_per_day_per_spacecraft": total * SECONDS_PER_DAY / 1e6,
            "total_mb_per_day_per_spacecraft": total * SECONDS_PER_DAY / 8e6,
            "warning": cfg["notes"]}

def compute(input_path="data/telemetry_generation_inputs.json", output_dir="outputs"):
    """Calculate subsystem engineering first, then feed computed rates to TT&C."""
    from .subsystem_models import compute as compute_subsystems
    model = compute_subsystems(telemetry_path=input_path, output_dir=output_dir)
    rows = []
    for r in model["subsystems"]:
        origin = "PDF" if r["telemetry_origin"] == "PDF_AGGREGATE_FALLBACK" else "PRELIMINARY_ESTIMATE"
        rows.append({
            "subsystem": r["subsystem"], "rate_bps": r["rate_bps"],
            "mbit_per_day": r["mbit_per_day"], "mb_per_day": r["mb_per_day"],
            "source_type": origin, "source": r["telemetry_origin"],
            "requires_confirmation": origin != "PDF",
            "components": r["channels"], "engineering": r["engineering"]
        })
    total = sum(r["rate_bps"] for r in rows)
    result = {"status": model["status"], "scope": model["scope"], "subsystems": rows,
              "total_rate_bps_per_spacecraft": total,
              "total_mbit_per_day_per_spacecraft": total * SECONDS_PER_DAY / 1e6,
              "total_mb_per_day_per_spacecraft": total * SECONDS_PER_DAY / 8e6,
              "warning": model["warning"]}
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "telemetry_generation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with (out / "telemetry_generation.csv").open("w", encoding="utf-8", newline="") as f:
        fields = ["subsystem", "rate_bps", "mbit_per_day", "mb_per_day", "source_type", "requires_confirmation", "source"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows({k: r[k] for k in fields} for r in rows)
    return result

if __name__ == "__main__":
    print(json.dumps(compute(), indent=2, ensure_ascii=False))
