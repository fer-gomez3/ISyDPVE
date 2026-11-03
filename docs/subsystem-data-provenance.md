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
