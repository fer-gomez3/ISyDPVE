# Optional reverse-engineered telemetry scenario

The default `data/telemetry_generation_inputs.json` remains **unchanged**. This alternative reconstructs the two PDF aggregate targets using explicit assumed channels, rather than injecting the PDF total as the output.

Run from repository root:

```bash
python main.py --telemetry-input data/telemetry_reverse_engineered_scenario.json --output-dir outputs/reverse_engineered
```

All downstream TT&C, OBDH, transfer planning, DSN and Excel outputs are generated using this scenario, not the baseline. Compare `outputs/reverse_engineered/telemetry_generation.json`, `telemetry_traceability.csv`, `data_generation_interface.csv`, and the workbook.

## Sensor-level calculation

Each complete channel contributes `count * bits_per_sample / interval_seconds` bits/s.

| Payload | Channels | Bits/sample | Period (s) | Calculated bps |
|---|---:|---:|---:|---:|
| Clock lock status | 1 | 8 | 1 | 8 |
| Clock cell temperatures | 4 | 16 | 1 | 64 |
| SSPA RF power | 1 | 16 | 1 | 16 |
| **Unresolved status budget** | 3 | 4 | 1 | 12 |
| **Total** | | | | **100** |

PDF §2.7.3 identifies the first three categories but not their bit depths, counts or cadences. All numeric inputs in this table are assumptions. **The 12 bps is a calibration residual, NOT evidence of three actual status sensors.** The exact PDF match is therefore not independent verification.

| Structures | Channels | Bits/sample | Period (s) | Calculated bps |
|---|---:|---:|---:|---:|
| Deployment switches | 8 | 1 | 2 | 4 |
| SADM encoders | 2 | 16 | 4 | 8 |
| HGA resolvers | 2 | 16 | 4 | 8 |
| Structural RTDs | 6 | 10 | 5 | 12 |
| **Total** | | | | **32** |

PDF §7.5.3 specifies the 8 switch bits, 2×16-bit SADM encoders, 2×16-bit HGA resolvers, and six RTDs at 0.2 Hz. The 2/4/4 s periods and 10-bit RTD resolution are **assumed**, not PDF values.

## Interpretation and safeguards

- The default baseline still uses PDF aggregate rates provisionally when channel itemisation is unknown; this scenario computes those rates from complete hypothesised inventories.
- Both scenarios total about **2301.74 bps per spacecraft** because the two reverse-engineered aggregates reproduce the reference. All other subsystem inventories remain provisional.
- `itemisation_complete: true` in this scenario means the **hypothesis accounts for the aggregate**, not that a subsystem owner confirmed its hardware. `requires_confirmation` remains true because channel parameters are assumptions.
- Changing a sample interval must change the calculated rate and produce a nonzero `difference_from_pdf_bps`; never automatically tune another parameter to hide the difference.
- The current code reports a generic complete-itemisation match. Read it together with the per-channel `ASSUMPTION` provenance: **a match is not validation**.
- Packetisation, headers, time tags, compression, event bursts, duty cycles, and whether the PDF aggregate includes protocol overhead are not established by these tables. Confirm with subsystem owners.
- Solar-panel power, EPS area, AOCS torques and propulsion sizing are **not** telemetry data rates. Their engineering equations must not be used to infer bps.
- Next step: replace assumed counts, resolutions and cadences with subsystem-owner data, and retain the PDF rate solely as a comparison target.

No changes were made to the baseline inputs, original tests, core calculation functions or Git history.
