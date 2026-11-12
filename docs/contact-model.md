# SELENA DSN geometry and provisional allocation

Run `python -m ttc.run_analysis` from the repository root.

Inputs: `data/contacts_master.csv`, 112 geometric windows from the previous propagator run (2020-01-01 to 2020-01-05). These are **not** DSN antenna reservations, nor the planned 2030 mission epoch.

Outputs (generated, not committed):
- `outputs/dsn_analysis.json`: per-satellite window counts, potential hours, gaps, ideal required bit rate for **known** 132 bit/s telemetry, optional buffer simulation, and subsystem interface placeholders.
- `outputs/candidate_dsn_schedule.csv`: hypothetical non-overlapping station/satellite assignments.

The planner assumes ONE station resource per DSN complex, one simultaneous HGA link per satellite and instantaneous handovers. Its fairness heuristic can produce many impractically short contacts. **Do not treat this as a real operational schedule or evidence of DSN availability.** No antenna allocation, acquisition, handover time, pointing slew, elevation/RF validation or 2030 geometry is included.

With no `--downlink-bps` input, the storage model intentionally assumes **zero transmitted data**, giving an accumulation reference, not a recommended buffer capacity. With `--downlink-bps 2000 --overhead 0.2`, results are an explicitly assumed scenario, not a derived RF link.

The ideal rate is total known data generated over the entire simulation divided by the total candidate contact time; it is **not sufficient to guarantee bounded peak buffer or daily downlink**. Unknown AOCS/EPS/TCS/propulsion/OBDH telemetry is never treated as zero in completeness reporting. PNT broadcast is not counted as DSN housekeeping.

To close the design: confirm sensor telemetry rates, regenerate 2030 geometry, set minimum usable contact durations and handover constraints, establish DSN antenna allocations, then perform RF link budget and power/thermal sizing.
