# Subsystem data provenance

Which numbers come from the PDF, which are calculated, which are placeholders and what is still pending. Nothing is fitted to match the PDF; differences are shown.

Labels: **DOC** = taken from the PDF; **CALC** = computed by the model; **ASSUMPTION** = placeholder chosen by the model authors; **UNKNOWN / INPUT NEEDED** = not available, never filled with a guess or zero.

## Telemetry (bit/s per satellite)

Rate of a channel = count x bits / interval, counted only if all three are known. Subsystem rate:
- With a PDF aggregate and incomplete itemisation: aggregate (provisional); unitemised remainder = aggregate - itemised.
- Itemised above the aggregate: itemised sum used, flagged `ITEMISED_EXCEEDS_PDF_AGGREGATE_INVESTIGATE`.
- Owner sets `itemisation_complete: true`: itemised sum used, difference from PDF shown.
- No inventory and no PDF value: `MISSING_INPUT`.

| Subsystem | Rate | Itemised | Remainder | Basis | Pending |
|---|---|---|---|---|---|
| Payload | 100 | 0 | 100 | DOC aggregate (PDF 2.7.3), provisional | Count, bits, cadence of clock lock status, clock cell temperatures, SSPA RF power |
| Structures | 32 | 0 | 32 | DOC aggregate (PDF 7.5.3), provisional | Cadence of 8 switch bits, 2x16-bit SADM encoders, 2x16-bit HGA resolvers; bit depth of the 6 RTDs (0.2 Hz is DOC) |
| AOCS | 1587.2 | 1587.2 | n/a | ASSUMPTION | Real channel list |
| Propulsion | 38.4 | 38.4 | n/a | ASSUMPTION | Real channel list |
| EPS | 140.8 | 140.8 | n/a | ASSUMPTION | Real channel list |
| Thermal | 96 | 96 | n/a | ASSUMPTION | Real channel list |
| OBDH | 307.34 | 307.34 | n/a | ASSUMPTION | Real channel list |
| **Total** | **2301.74** | 2169.74 | 132 | | |

Per-channel detail: `outputs/telemetry_traceability.csv`. Single code path: `ttc/subsystem_models.telemetry_rows` feeds the interface CSV/JSON, the per-satellite outputs, the downlink simulation and the Excel Telemetry sheet.

## Engineering equations (size hardware, do not set telemetry rates)

| Item | Status |
|---|---|
| EPS: A = P_sa / P_EOL, P_EOL = P0 Id cos(theta) (1-d)^L | CALC. Required solar power 387.8 W vs PDF array 410 W (-22.2 W); battery 1797.9 Wh vs PDF 1800 Wh (-2.1 Wh); area 0.917 m^2 (PDF gives no area; 410 W would need 0.969 m^2 at the modelled specific power) |
| EPS `cell_specific_power_w_m2` = 500 | ASSUMPTION, unchanged; about 37 % efficiency at 1361 W/m^2 looks high |
| EPS `eclipse_hours` = 6.5068 | ASSUMPTION; reproduces 1.8 kWh, orbit not defined |
| AOCS gravity gradient | CALC at the radius given; periapsis and apoapsis radii are INPUT NEEDED, so 6200 km is a circular lower bound. Formula for the variable radius is implemented |
| AOCS wheel torque | CALC: (slew + gravity gradient) x margin; other disturbances missing |
| Propulsion, thermal, structures, OBDH memory | ASSUMPTION inputs, lecture equations |

## Owner TODOs

- **Payload owner:** channel count, bits and cadence for the three named channels; whether 100 bps includes headers.
- **Structures/mechanisms owner:** missing cadences, RTD bit depth, whether 32 bps includes headers.
- **AOCS, Propulsion, EPS, Thermal, OBDH owners:** real channel inventories.
- **Mission analysis:** orbit (periapsis, apoapsis), eclipse duration; use the same orbit for EPS and AOCS.
- **EPS owner:** cell specific power, eclipse hours, array area.
- **AOCS owner:** other disturbance torques, wheel margin.
- Link-budget and DSN inputs remain as listed in `docs/technical-report.md`.


## Telemetry calculation policy (2026-11-03)

**Decision:** use documented PDF subsystem aggregate rates for nominal TT&C sizing **only while the sensor inventory is incomplete**. Keep the sensor-level equation and all missing variables explicit so the rate can be calculated when the subsystem owner provides the values. Do not invent missing channels, quantization or sampling frequencies to reproduce the aggregate. The alternative `data/telemetry_reverse_engineered_scenario.json` is a separate illustrative what-if scenario, **not** the accepted baseline.

For each channel `i`:

```python
# Sensor-level telemetry equation (bits/second):
# R_i = count_i * bits_per_sample_i / interval_seconds_i
# R_subsystem = sum(R_i for i in all nominal housekeeping channels)
# Required inputs for EVERY channel: count, bits_per_sample, interval_seconds.
# The subsystem owner must also confirm that the channel inventory is complete.
# If any required parameter is unknown, keep it null and retain PDF fallback.
# Once itemisation_complete is owner-confirmed, calculate from channels;
# show the difference against the PDF reference instead of forcing a match.
```

### Payload (PDF §2.7.3)

```text
R_payload = (N_lock * B_lock / T_lock)
          + (N_temp * B_temp / T_temp)
          + (N_sspa * B_sspa / T_sspa)
          + R_other_confirmed_channels
PDF fallback: 100 bps (provisional)
```

The PDF identifies clock-lock status, clock-cell temperatures and SSPA RF power but does not supply their channel counts, quantisation or sampling periods. `R_other_confirmed_channels` is **not** an invented 12 bps filler: it is a reminder to ask whether other channels, timestamps, packet headers or events are included in the PDF aggregate. No numerical value is assigned.

### Structures/mechanisms (PDF §7.5.3)

```text
R_structures = 8 / T_switch
             + 2*16 / T_SADM
             + 2*16 / T_HGA
             + 6*B_RTD / 5
PDF fallback: 32 bps (provisional)
```

The PDF provides eight switch bits, two 16-bit SADM encoders, two 16-bit HGA resolvers, and six RTDs at 0.2 Hz (5-second sampling). The switch, SADM and HGA sampling periods and RTD resolution are **UNKNOWN**, not zero. All other channel inventories also use the same `count * bits / interval` equation and must be verified by their owners.

### Selection and traceability

- **PDF_FALLBACK**: existing output label `rate_basis=PDF_AGGREGATE_PROVISIONAL` when itemisation is incomplete and a PDF reference exists.
- **CALCULATED**: existing `rate_basis=CHANNELS_ITEMISATION_COMPLETE` when `itemisation_complete=true`. The owner must verify the inventory, and assumed parameters remain flagged `ASSUMPTION`.
- **ASSUMED**: existing `rate_basis=CHANNELS_ASSUMED` for provisional channel-derived rates without a PDF reference.
- **MISSING_INPUT**: no valid channel rate and no reference; never silently assume 0 bps.

These labels describe the selection policy; the actual machine-readable names are the existing `rate_basis` values above. The exported `itemised_bps`, `unitemised_remainder_bps`, `pdf_reference_bps`, `difference_from_pdf_bps`, `incomplete_channels` and per-variable provenance must remain visible. The PDF fallback is a **sizing input**, not an independently calculated sensor rate. Hardware sizing equations (EPS solar array, AOCS torque, etc.) are separate from sensor data generation.
