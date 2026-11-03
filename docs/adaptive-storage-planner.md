# SELENA adaptive OBDH memory and contact planning — preliminary

Run from the repository root:

```bash
python -m ttc.adaptive_storage
```

Outputs: `outputs/adaptive_storage_summary.json`, `outputs/adaptive_storage_history.csv`, and `outputs/adaptive_contact_schedule.csv`.

## Scope

- Each of eight spacecraft has its **own** OBDH storage. Three orbital groups (3+3+2) do not share physical memory.
- All eight spacecraft use the same preliminary memory capacity; they can receive different contact times.
- Telemetry rates are derived from the existing subsystem inventory; event multipliers can temporarily increase selected streams.
- Candidate visibility windows are read from `data/contacts_master.csv`, calculated for 2020, and **translated on the calendar** to 2030. This does **not** recompute orbital geometry.
- The algorithm considers geometric visibility, per-station enabled/outage intervals, one simultaneous link per station and per spacecraft, setup time, minimum useful transmission, shared daily DSN hours, and stream priorities.
- It greedily selects contact starts at 5-minute intervals, favoring higher risk of filling memory or exceeding delivery intervals. It sizes contact duration based on pending data and the effective downlink rate.
- The 24-hour limit is a **scenario requirement**: at least one successful download per spacecraft every 24 hours. The algorithm reports violations when opportunities or allocated resources are insufficient; it does not fabricate contacts.
- Station outages and the event in the example config are *illustrative inputs*. A future mission operations timeline and actual DSN allocations must replace them.

## Known limitations

This is a **preliminary heuristic**, not an optimized or flight-qualified mission scheduler. It does not verify real DSN bookings, HGA steering, antenna slews, eclipse-dependent RF constraints, Earth-spacecraft range variation, packet loss, ACK/retransmission, real space-weather forecasts, or memory corruption. The oldest-data-age warning uses backlog divided by **nominal** generation rate; this is only a proxy when events alter the rate. It does not enforce a hard 24-hour guarantee when DSN resources are insufficient.

The scheduler currently plans using **memory and latency urgency**, not a full integer-programming optimum. The capacity of 1024 Mbit per spacecraft, 15% reserve, 70/85/95% warning thresholds and event burst are **editable illustrative values**, not hardware specifications.

## Validation before design freeze

1. Obtain an actual OBDH memory allocation and engineering margin.
2. Validate nominal and event-driven telemetry generation with each subsystem.
3. Replace hypothetical DSN daily hours and station availability with actual planning assumptions.
4. Introduce a timestamped FIFO packet queue to evaluate exact data age during bursts.
5. Integrate HGA pointing and link-budget variations, plus independent scheduling optimization.
6. Run sensitivity cases for memory capacity, event severity, DSN access and setup overhead.
