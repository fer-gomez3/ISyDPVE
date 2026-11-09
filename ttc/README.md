# SELENA — TT&C / DSN visibility

Two separate tools:

1. `python -m ttc.contacts data/raw/Contactos_con_DSN.txt`: import **previously calculated** contact windows.
2. `python -m ttc.visibility data/raw/satellite_ephemeris.csv`: compute **sampled geometric visibility** from lunar spacecraft positions and time-dependent Earth station positions.

See [`ephemeris_format.md`](ephemeris_format.md) for the strict input coordinate-frame contract. The visibility module does **not yet** extract precise start/end contact windows; this is the next development step.

Install dependencies with `pip install -r requirements.txt` and run `python -m pytest`.

The original 112-contact propagator export and actual spacecraft ephemerides have not yet been uploaded. Station coordinates are approximate and DSN antenna allocation is not modeled.


## OBDH and RF sizing (2026-11-10 development)

Run `python -m ttc.obdh_report --downlink-bps 256000 --overhead 0.2`
to produce `outputs/obdh/summary.json`, per-satellite `*_timeline.csv`
and `*_timeline.png` when matplotlib is installed. This is a **scenario**:
historical candidate contacts are not confirmed DSN grants, 256 kbps is
illustrative, and only the documented 132 bps housekeeping subtotal is used.
A successful discharge is not evidence that unknown subsystem data fit.

Run `python -m ttc.communications_budget` for RF and power outputs.
`minimum_required_antenna` reports `MISSING_RF_POWER_CAP` until a
documented maximum RF transmitter power is provided. Once supplied,
`ttc.antenna_sizing.minimum_diameter` solves for a minimum diameter
within configurable physical bounds, subject to the RF link assumptions.
It does not select or mass-budget flight hardware.

Run `python -m pytest tests/test_obdh_timeline.py tests/test_communications_budget.py`.
These tests still need execution in an environment with the repository
dependencies; adding tests is not equivalent to passing them.

Known remaining limitations: final DSN grants, antenna conflicts and acquisition,
per-stream deadlines, missing telemetry rates, actual EPS/TCS hardware draws,
and flight-qualified X/Ka link inputs. Do not label the pipeline flight-validated.


## Integrated preliminary DSN-to-OBDH workflow

Run `python -m ttc.dsn_pipeline --downlink-bps 256000 --overhead 0.2 --minimum-contact-seconds 300`.
This writes `outputs/dsn_pipeline/candidate_schedule.csv`, `summary.json`,
and one `*_obdh.csv` per spacecraft. The allocation is a deterministic
earliest-end heuristic, not a globally optimized DSN booking. Its optional
station availability is an input scenario, not measured DSN availability.
The 24h gap check applies to the supplied analysis horizon only; a compliant
historical window does not establish compliance for the 2030 mission.
For visualizations run `python -m ttc.obdh_report` (which currently uses
the older candidate schedule, not the new allocator). Until unified,
do **not** present its charts as plots of the integrated schedule.

Remaining engineering work: per-stream deadlines/priority, source-resolved
telemetry, actual availability and acquisition, EPS/TCS closure, real antenna
power cap, integrated plots, full test execution and PDF reconciliation.
