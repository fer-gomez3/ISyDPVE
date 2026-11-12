"""Estimate requested DSN reservation from OBDH backlog at visibility-window start.

Planning only: no overlapping reservations are created here. The scheduler remains
the authority for station conflicts and shared daily DSN budget.
"""
from datetime import datetime
import bisect
import csv

def estimate_requests(windows, timelines, generation_bps, gross_bps, overhead,
                      preparation_seconds, teardown_seconds, minimum_tx_seconds,
                      output_path):
    if gross_bps <= 0 or not 0 <= overhead < 1 or generation_bps < 0:
        raise ValueError("Invalid link or generation rates")
    net_bps = gross_bps * (1 - overhead) - generation_bps
    rows = []
    for window in sorted(windows, key=lambda w: (w["start"], w["satellite"], w["station"])):
        sat = window["satellite"]
        times, buffers = timelines[sat]
        idx = bisect.bisect_right(times, window["start"]) - 1
        backlog_bits = buffers[max(0, idx)] * 1e6
        available_s = (window["end"] - window["start"]).total_seconds()
        tx_s = backlog_bits / net_bps if net_bps > 0 else None
        # New telemetry continues to be generated while the downlink is active.
        # No fixed percentage split or duplicate reception is assumed.
        requested_s = (preparation_seconds + teardown_seconds +
                       max(minimum_tx_seconds, tx_s)) if tx_s is not None else None
        fits = requested_s is not None and requested_s <= available_s
        rows.append({
            "satellite": sat, "station": window["station"],
            "visibility_start_utc": window["start"].isoformat(),
            "visibility_end_utc": window["end"].isoformat(),
            "visibility_minutes": round(available_s / 60, 3),
            "backlog_at_start_mbit": round(backlog_bits / 1e6, 4),
            "generation_bps": generation_bps,
            "effective_downlink_bps": gross_bps * (1 - overhead),
            "net_drain_bps": net_bps,
            "required_useful_tx_minutes": None if tx_s is None else round(tx_s / 60, 3),
            "requested_reservation_minutes": None if requested_s is None else round(requested_s / 60, 3),
            "fits_geometric_window": fits,
            "status": "FITS_VISIBILITY_ONLY_NOT_ALLOCATED" if fits else "NOT_FEASIBLE_IN_WINDOW",
        })
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ["satellite"])
        writer.writeheader()
        writer.writerows(rows)
    return rows
