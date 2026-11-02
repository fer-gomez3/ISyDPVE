# SELENA: inputs and cross-subsystem outputs

Source: **Subsystems PDF**, 66 pages. The report's section 6, *Communication and Data Handling*, is blank (PDF p.50). The numbers below are extracted from other sections, **not** a completed TT&C design.

## Source-backed inputs (per satellite)

| Interface | Rate or allocation | Source |
|---|---:|---|
| Payload housekeeping to OBDH | 100 bit/s = 8.64 Mbit/day | PDF p.20, §2.7.3 |
| Structures/mechanisms housekeeping | 32 bit/s = 2.7648 Mbit/day | PDF p.58, §7.5.3 |
| PNT AFS-I broadcast to lunar users | 250 bit/s = 21.60 Mbit/day | PDF p.16, Table 4 |
| PNT AFS-Q pilot information | 0 bit/s | PDF p.16, Table 4 |
| TT&C XU3 uplink file size | 0.10–1.00 Mbit/day | PDF pp.17,20 |
| Illustrative XU3 net uplink | ~2 kbit/s | PDF p.20, §2.7.3 |
| Electrical bus | 28 V | PDF p.20 and p.32 |
| Platform total nominal / peak | 311 / 336 W | PDF p.32 |
| Battery | 1800 Wh | PDF p.35 |
| TT&C + OBDH mass allocation | 11.40 kg | PDF p.59, Table 32 |
| Structures mechanisms operational load | 5.2 W | PDF p.58, §7.5.3 |

**Caution:** Table 4 gives a broad XD3 payload telemetry volume of ~4.32–43.20 Mbit/day; §2.7.3 specifies 100 bit/s (8.64 Mbit/day). We use the latter as the provisional payload housekeeping baseline and retain this discrepancy for reconciliation.

The 25 W RF output, 154 W DC nominal payload, and 35.7% PA efficiency are **lunar PNT broadcast**, not DSN X/Ka TT&C transmitter specifications. PNT service bits must not automatically be counted as stored TT&C telemetry. The 311 W platform load already includes 154 W payload load.

## Reproducible model

`ttc/engineering_inputs.py`: centralized, sourced, importable constants. Unknown rates and DSN link parameters remain `None`.

`ttc/engineering_calculations.py`: computes daily data volume per subsystem, known subtotal, incomplete total flag, provisional downlink rate given **usable** contact time and protocol overhead, and interface outputs for OBDH, TT&C, EPS, thermal and AOCS.

Run from repository root:

```bash
python -m ttc.engineering_calculations
pytest -q
```

JSON output: `outputs/subsystem_interfaces.json` (generated, gitignored).

To import into other engineering code:

```python
from ttc.engineering_calculations import calculate
results = calculate(contact_seconds=1800, overhead_fraction=0.2)
print(results["ttc"])
print(results["eps"])
```

The contact time is **not** the raw geometry window unless DSN antenna allocation, station conflicts, RF feasibility and pointing have been established.

## Needed to close the interfaces

- Each team's confirmed net housekeeping rate and duty cycle (AOCS, EPS, TCS, propulsion, OBDH).
- DSN link frequency, ground G/T, spacecraft antenna gain, range, losses, coding and required link margin.
- Actual DSN allocated contacts and usable seconds per spacecraft.
- TT&C transmitter DC consumption and RF efficiency, plus thermal dissipation.
- OBDH maximum contact gap, packet overhead, compression and storage margin.

Do not interpret unknown values as zero. Interface outputs intentionally remain null until inputs are justified.
