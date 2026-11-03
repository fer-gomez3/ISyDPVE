# SELENA — Public technical overview (preliminary)

SELENA is a university conceptual study of an eight-spacecraft lunar positioning, navigation and timing constellation. This document describes the preliminary TT&C/OBDH model without representing estimates as validated flight requirements.

## Communications and data handling

- An X-band Earth downlink is studied using an idealized circular-aperture HGA, a preliminary 0.38 m diameter and assumed 60% aperture efficiency. These are **not selected hardware specifications**.
- The TT&C + OBDH **mass allocation is 11.40 kg per spacecraft**, not a validated itemized bill of materials. The two-axis HGA gimbal is allocated to Structures, so it must not be counted twice.
- The data-generation model uses 100 bps for payload housekeeping (PDF provisional) and 32 bps for Structures (PDF). ADCS, EPS, Thermal, Propulsion and OBDH are modeled from **hypothetical sensor/channel inventories requiring confirmation**.
- The current scenario generates approximately **2,301.74 bps**, or **24.86 MB/day per spacecraft** (198.87 MB/day across eight spacecraft), excluding exceptional event bursts and communications overhead. Lunar PNT broadcast is separate from Earth telemetry.
- Link feasibility, power consumption, onboard buffer, and DSN downlink scheduling remain **preliminary** until actual geometry, RF hardware, data rates and ground network allocations are confirmed.
- Shifted historical contact timestamps are **not** a physical orbit propagation for 2030. Hypothetical DSN allocation is **not** a reservation.

## Reproducibility

Run from repository root with Python 3.11+:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
python main.py
```

Expected outputs include `outputs/telemetry_generation.json`, `outputs/telemetry_generation.csv`, `outputs/overview.json`, and `outputs/SELENA_TTC_Model.xlsx`. Output availability is subject to successful installation and execution; no end-to-end certification is implied.

## Open validation items

Confirm telemetry source tables and packet overhead; import real 2030 lunar orbit propagation and Earth station geometry; close HGA pointing and uplink/downlink budgets; verify EPS/TCS interfaces, DSN service constraints and component mass allocations.
