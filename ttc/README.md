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
and one `*_obdh.csv` per spacecraft. The allocation comes from the unified
scheduler (`ttc/dsn_scheduler.py`, see below): a deterministic heuristic with a
coverage guarantee, not a globally optimized DSN booking. Its optional
station availability is an input scenario, not measured DSN availability.
The 24h gap check applies to the supplied analysis horizon only; a compliant
historical window does not establish compliance for the 2030 mission.
For visualizations run `python -m ttc.obdh_report` (which currently uses
the older candidate schedule, not the new allocator). Until unified,
do **not** present its charts as plots of the integrated schedule.

Remaining engineering work: per-stream deadlines/priority, source-resolved
telemetry, actual availability and acquisition, EPS/TCS closure, real antenna
power cap, integrated plots, full test execution and PDF reconciliation.


## Confirmed versus estimated telemetry in DSN pipeline

The DSN pipeline now accepts `--telemetry-profile confirmed` (default) or
`--telemetry-profile scenario`. Example:

```bash
python -m ttc.dsn_pipeline --telemetry-profile confirmed --output-dir outputs/dsn_confirmed
python -m ttc.dsn_pipeline --telemetry-profile scenario --output-dir outputs/dsn_scenario
python -m pytest -q tests/test_dsn_telemetry_profiles.py
```

`confirmed` uses only the documented 100+32 bps subtotal; unconfirmed
subsystems are missing, **not zero**. `scenario` imports all seven
channel-derived stream rates from the same inputs used by
`integrated_preliminary`; the extra streams are explicitly assumptions.
Both modes currently share the simpler DSN allocator and do not yet enforce
per-stream deadlines or the detailed operational policy of
`integrated_preliminary`. The scenario totals are not a replacement for
subsystem-owner verification. The newly added regression tests have not
been independently executed in this session.


## DSN policy + deadline-aware integrated output (current development)

Run:

```bash
python -m ttc.dsn_pipeline --telemetry-profile confirmed --output-dir outputs/dsn_confirmed
python -m ttc.dsn_pipeline --telemetry-profile scenario --output-dir outputs/dsn_scenario
python -m pytest -q tests/test_operational_interfaces.py tests/test_dsn_telemetry_profiles.py
```

The pipeline uses `data/dsn_operational_policy.json` to deduct acquisition,
preparation and teardown from candidate contacts. Its `deadline_results`
simulates per-stream delivery ages and priority for either the documented
132 bps subtotal or seven-stream assumed scenario. Per-satellite `*_obdh.png`
plots show buffer, cumulative downlink and TX activity, alongside CSV data.
`report_comparison.csv` compares report inputs to modeled values and
marks unclosed mass/power interfaces. `electrical_thermal` is reported
per satellite; electrical and thermal totals remain **null** until the
required independent component power draws and radiated RF power are known.

**Limits:** heuristic station assignment is not deadline-optimized;
availability is hypothetical; 2020 geometric windows are not 2030 ephemerides.
No spacecraft flight EPS/TCS closure or DSN bookings are claimed. A
passing unit test does not resolve missing source inputs. New commits must
pass GitHub Actions before being called validated.

## Unified DSN contact scheduler (`ttc/dsn_scheduler.py`)

`dsn_pipeline` and `integrated_preliminary` now share one assignment criterion.
It replaces the earliest-end whole-window greedy and the separate adaptive
rolling scheduler as the source of contacts (legacy modules stay available).

Constraints respected: geometric visibility windows, one satellite per station
and one station per satellite at a time, preparation (45 + 10 min), teardown
(15 min), minimum useful TX (5 min) and the shared 3 h per UTC day budget counted
on the full reservation. Only the TX part moves data.

Policy, in order:
1. **Coverage guard** – an exact search (5-min grid) decides whether all 8
   satellites can be served. If so, minimal anchor contacts are reserved so the
   heuristic cannot starve any satellite (e.g. SELENA_12/13). If not, the best
   feasible subset is scheduled and `diagnostics.coverage.analysis` names the
   binding constraints (`GEOMETRY`, `STATION_AVAILABILITY`, `DAILY_BUDGET`,
   `STATION_CONFLICT`, `SEARCH_LIMIT`).
2. **Critical deadlines first** – streams whose slack is at most one minimal
   pass, ordered by priority at risk.
3. **Equity** – remaining budget goes to the satellite with the least usable
   contact time so far.

It is a deterministic heuristic with a coverage guarantee, not a proven optimum,
and it never forces a positive result: `deadline_explanation` in the summary
states whether unmet deadlines come from the daily budget, geometry, station
availability or transmission rate.

Result in the current scenarios: all 8 satellites get contacts, but deadlines
are still missed. The cause is the 3 h/day budget (holding a 6 h deadline over
96 h needs >= 16 passes per satellite, roughly 160 h versus about 14 h
available), not geometry (union gap <= 0.28 h) nor link rate.

**The historical 2020 windows are not confirmed DSN availability for 2030.**
The 3 h/day budget and the 55/15 min policy are user-supplied hypotheses.

Before/after: `python -m ttc.allocator_comparison` writes
`outputs/allocator_comparison/allocator_comparison.{csv,json,md}`. The legacy
pipeline allocator delivered more volume only because it ignored the daily
budget (about 140 h reserved versus 15 h).


## PDR closeout deliverables

- `docs/SELENA_TTC_OBDH_PDR_preliminary.md` — preliminary PDR text,
  baseline comparison, RF/EPS/TCS open interfaces and explicit limitations.
- `python -m ttc.dsn_sensitivity --hours 1 3 6 12 24` — compare
  shared DSN daily-hour budgets under identical scheduling and telemetry
  assumptions; exports CSV, JSON and (if matplotlib available) PNG.
- `python -m pytest -q tests/test_dsn_sensitivity.py` — regression checks.

**No design compliance is implied** until physical 2030 geometry, DSN
allocation, approved stream deadlines, RF hardware and EPS/TCS inputs
are verified. These newest changes require fresh CI validation.

## OBDH memory: shared pool with logical queues per subsystem (`ttc/memory_queues.py`)

Each satellite has its own independent OBDH memory (scenario values: 1024 Mbit,
870.4 usable, 153.6 reserve; levels 65 % preventive and 70/85/95 % watch/urgent/
critical, from `data/adaptive_storage_scenario.json`). The memory is a **shared
pool**: there are no physical partitions or fixed quotas per subsystem. Inside it
the data are organised **logically** into one FIFO queue per stream with priority,
age of the oldest bit and maximum delivery age. Downlink order is earliest
deadline first, priority as tie breaker. Telemetry is never reduced or dropped.

`dsn_pipeline` and `integrated_preliminary` now write `memory_queues.csv`
(per satellite and stream, sampled every 30 min) and `memory_queues_summary.json`:
generated vs downloaded data (per satellite and for the constellation), queue
Mbit per subsystem at the total peak, peak per queue, oldest age against the
maximum age, and first crossing of each level. Capacity, reserve and levels are
simulation values, not approved requirements nor a selected memory device.
Generated data is not the same as downloaded data.
