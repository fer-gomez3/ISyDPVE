"""Reproducible data/communications calculations and cross-subsystem outputs.

Run: python -m ttc.engineering_calculations
All unknowns remain null in the output. No assumed DSN availability or RF design.
"""
import json
from pathlib import Path
from .engineering_inputs import (
    SECONDS_PER_DAY, TELEMETRY, PNT_BROADCAST, TTNC_UPLINK, PLATFORM, DSN_LINK,
)

def calculate(contact_seconds=None, overhead_fraction=0.0, other_rates_bps=None):
    """Compute per-spacecraft daily telemetry and interfaces.

    contact_seconds: usable seconds for ONE spacecraft over one day, not geometric
      visibility unless DSN availability, antenna conflicts and pointing are resolved.
    overhead_fraction: fraction of downlink capacity consumed by protocol overhead.
    other_rates_bps: optional measured/approved rates keyed by telemetry source name.
    """
    if contact_seconds is not None and not (0 < contact_seconds <= SECONDS_PER_DAY):
        raise ValueError("contact_seconds must be in (0, 86400]")
    if not (0 <= overhead_fraction < 1):
        raise ValueError("overhead_fraction must be in [0, 1)")
    other_rates_bps = other_rates_bps or {}
    valid = {s.name for s in TELEMETRY}
    if set(other_rates_bps) - valid:
        raise ValueError("Unknown telemetry source")
    if any(v is None or v < 0 for v in other_rates_bps.values()):
        raise ValueError("Rates must be nonnegative numbers")

    rows = []
    for s in TELEMETRY:
        rate = other_rates_bps.get(s.name, s.rate_bps)
        rows.append({
            "subsystem": s.name, "rate_bps": rate,
            "daily_mbit": None if rate is None else rate * SECONDS_PER_DAY / 1e6,
            "source": s.source, "note": s.note,
        })
    known = sum(r["daily_mbit"] for r in rows if r["daily_mbit"] is not None)
    missing = [r["subsystem"] for r in rows if r["daily_mbit"] is None]
    complete = not missing
    required = (known * 1e6 / (contact_seconds * (1 - overhead_fraction))
                if contact_seconds is not None else None)
    return {
        "scope": "per spacecraft per 24h",
        "telemetry": rows,
        "known_daily_mbit": known,
        "total_daily_mbit": known if complete else None,
        "missing_rates": missing,
        "contact_seconds_usable": contact_seconds,
        "overhead_fraction": overhead_fraction,
        "minimum_downlink_bps_for_known_data": required,
        "minimum_downlink_bps_for_all_data": required if complete else None,
        "obdh": {
            "minimum_buffer_mbit_for_one_day_known_only": known,
            "minimum_buffer_mbit_for_one_day_all": known if complete else None,
            "required_memory_mbit": None,
            "note": "Final buffer depends on gaps between usable DSN contacts, burst production, margin and schedule.",
        },
        "ttc": {
            "required_net_downlink_bps_known_only": required,
            "required_net_downlink_bps_all": required if complete else None,
            "uplink": TTNC_UPLINK,
            "link_design": DSN_LINK,
            "note": "RF TX power cannot be derived from data volume alone: requires frequency, geometry, antennas, G/T, losses and Eb/N0.",
        },
        "eps": {
            "platform_reference": PLATFORM,
            "incremental_ttc_tx_dc_w": None,
            "incremental_ttc_contact_energy_wh": None,
            "note": "311 W platform total already includes payload; do not double count.",
        },
        "thermal": {
            "incremental_ttc_heat_w": None,
            "note": "Needs RF PA efficiency and TT&C electronics electrical consumption.",
        },
        "aocs": {
            "required_hga_pointing_windows": None,
            "note": "Derived from scheduled contacts, not raw geometric visibility.",
        },
        "payload": PNT_BROADCAST,
        "data_completeness": "complete" if complete else "partial",
    }

def export_json(path, **kwargs):
    result = calculate(**kwargs)
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return result

if __name__ == "__main__":
    print(json.dumps(export_json("outputs/subsystem_interfaces.json"), indent=2))
