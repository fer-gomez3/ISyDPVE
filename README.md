# SELENA TT&C / OBDH preliminary model

Preliminary model of the Earth link (TT&C) and on-board data handling (OBDH) of the 8-satellite SELENA lunar PNT constellation (UPM course ISyDPVE). It generates telemetry budgets, an X-band link budget, HGA sizing, DSN time allocation, backlog simulation, power/heat interfaces and a formula-based Excel workbook.

> **Status.** Preliminary. Contact windows are the historical 2020 geometry **shifted to 2030 as a hypothetical scenario, not orbit propagation**. DSN allocation, setup time, downlink rate and most telemetry inventories are **assumptions**, not verified requirements. See [`docs/technical-report.md`](docs/technical-report.md).

## Install and run (Python 3.11 or 3.12)

```bash
git clone -b feature/ttc-initial-structure https://github.com/fer-gomez3/ISyDPVE.git
cd ISyDPVE
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt     # Windows: .venv\Scripts\python
.venv/bin/python -m pytest -q                           # unit, regression and integration tests
.venv/bin/python main.py                                # full scenario -> outputs/
```

Run from the repository root (scenario paths are relative). Results go to `outputs/`; `results/` holds a committed reference run (`python main.py --output-dir results`).

## Outputs

| File | Content |
|---|---|
| `outputs/SELENA_TTC_Model.xlsx` | Formula-based workbook: Inputs, Telemetry, Capacity, HGA, Link, Power (live formulas), Satellites, Stations, DSN Allocation, Downlink Contacts, RF Trade Cases, Checks, Limitations |
| `outputs/per_satellite/SELENA_xx.json`, `outputs/per_satellite_summary.csv` | Results for each of the 8 satellites |
| `outputs/data_generation_interface.csv`, `.json` | **Data generated per subsystem for the satellite-to-Earth calculations**: rate, bits/day, priority, maximum data age, origin, PDF reference, validation status, totals per spacecraft and constellation |
| `outputs/subsystem_engineering.json` | Preliminary engineering outputs per subsystem (placeholders) |
| `outputs/overview.json` | Run summary and statuses |
| `outputs/*.json`, `*.csv` | Telemetry, link, HGA, power, DSN allocation, downlink simulation, trade study |

In the workbook, edit the blue input cells on `Inputs` and `Telemetry`; the calculations update. Colours: green = documentation, yellow = assumption, blue = calculated, red = `INPUT NEEDED`. Link and power cells show `INPUT NEEDED` until distance, DSN G/T, required Eb/N0, losses, margin, PA efficiency and electronics power are provided (`data/link_budget_inputs.json`).

## Where to change parameters

| Parameter | File |
|---|---|
| Downlink rate (256 kbps), protocol overhead, DSN setup (15 min), minimum useful transmit, DSN hours/day, number of satellites | `data/ttc_parameters.json` (single source) |
| Sensor counts, sample sizes, intervals | `data/telemetry_generation_inputs.json` (or `python main.py --telemetry-input my_inventory.json` for a what-if run) |
| HGA diameter, efficiency, frequency, masses | `data/hga_preliminary_design.json` |
| Link inputs (distance, G/T, Eb/N0, losses, margin, RF power, PA efficiency) | `data/link_budget_inputs.json` |
| Priorities and data-age deadlines | `data/telemetry_detailed_scenario.json`, `data/transfer_requirements.json` |

## Using real ephemerides later

Provide contact windows as CSV (`contact_id, station, satellite, start_utc, end_utc`), then run `python main.py --contacts my_windows.csv --no-epoch-shift`. See `ttc/ephemeris_format.md` for the ephemeris contract. No orbit propagator is included.

## Known limitations

See section 6 of the technical report. Inputs still needed from other subsystems are in section 7.
