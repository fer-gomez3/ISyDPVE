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
| Payload | 100 | 100 | 0 | REVERSE_ENGINEERED_ESTIMATE, unverified | Count, bits, cadence of clock lock status, clock cell temperatures, SSPA RF power |
| Structures | 32 | 32 | 0 | REVERSE_ENGINEERED_ESTIMATE, unverified | Cadence of 8 switch bits, 2x16-bit SADM encoders, 2x16-bit HGA resolvers; bit depth of the 6 RTDs (0.2 Hz is DOC) |
| AOCS | 1587.2 | 1587.2 | n/a | ASSUMPTION | Real channel list |
| Propulsion | 38.4 | 38.4 | n/a | ASSUMPTION | Real channel list |
| EPS | 140.8 | 140.8 | n/a | ASSUMPTION | Real channel list |
| Thermal | 96 | 96 | n/a | ASSUMPTION | Real channel list |
| OBDH | 307.34 | 307.34 | n/a | ASSUMPTION | Real channel list |
| **Total** | **2301.74** | 2301.74 | 0 | | |

Per-channel detail: `outputs/telemetry_traceability.csv`. Single code path: `ttc/subsystem_models.telemetry_rows` feeds the interface CSV/JSON, the per-satellite outputs, the downlink simulation and the Excel Telemetry sheet.

## Reverse-engineered telemetry calibration (unverified)

The mission PDF is the **calibration target**, not a direct override of sensor calculations. Each rate is obtained from \(R=\\sum N_i b_i/T_i\). **All inferred parameters remain ASSUMPTION**, even when the resulting rate equals the PDF. The labels `REVERSE_ENGINEERED_ESTIMATE` and `REVERSE_ENGINEERED_MATCH_UNVERIFIED` prevent presenting this as independent validation.

| Payload channel | Count | Bits/sample | Interval (s) | bps |
|---|---:|---:|---:|---:|
| Clock lock status | 1 | 8 | 1 | 8 |
| Clock temperatures | 4 | 16 | 1 | 64 |
| SSPA RF power | 1 | 16 | 1 | 16 |
| Unresolved status words **(calibration residual, NOT confirmed sensors)** | 3 | 4 | 1 | 12 |
| **Payload total** | | | | **100** |

| Structures channel | Count | Bits/sample | Interval (s) | bps |
|---|---:|---:|---:|---:|
| Deployment switches | 8 | 1 | 2 | 4 |
| SADM encoders | 2 | 16 | 4 | 8 |
| HGA resolvers | 2 | 16 | 4 | 8 |
| RTDs | 6 | 10 | 5 | 12 |
| **Structures total** | | | | **32** |

**PDF-derived facts:** Structures channel counts and switch/encoder/resolver word sizes, RTD cadence; Payload names of three telemetry categories. **Inferences:** every other number in these two tables. The Payload 12 bps residual is a modelling placeholder, not a claim that the PDF lists three 4-bit status sensors. In particular, the Structures 10-bit RTD resolution and 2/4/4-second cadences are provisional. Owner must replace these values; a mismatch after replacement should be reported, not forcibly re-calibrated.

**Sensitivity:** doubling the clock lock sample interval from 1 to 2 seconds changes Payload from 100 to 96 bps, which must propagate through the Earth-link calculation and Excel. The PDF remains 100 bps as a reference, with a -4 bps delta.

**TT&C scope:** Hardware sizing (EPS power/area, AOCS torque, propellant mass) is not a data-rate calculation. It remains in a separate reference report and never feeds the telemetry generator.

## Owner TODOs

- **Payload owner:** channel count, bits and cadence for the three named channels; whether 100 bps includes headers.
- **Structures/mechanisms owner:** missing cadences, RTD bit depth, whether 32 bps includes headers.
- **AOCS, Propulsion, EPS, Thermal, OBDH owners:** real channel inventories.
- **Mission analysis:** orbit (periapsis, apoapsis), eclipse duration; use the same orbit for EPS and AOCS.
- **EPS owner:** cell specific power, eclipse hours, array area.
- **AOCS owner:** other disturbance torques, wheel margin.
- Link-budget and DSN inputs remain as listed in `docs/technical-report.md`.

## TT&C / OBDH scope correction (2026-11-03)

**Engineering clarification:** The relevant output from another subsystem is its generated housekeeping / event data, **not** its solar-panel power, battery energy, reaction-wheel torque, propellant mass, thermal equilibrium or structural safety factor. These hardware-sizing results must never determine telemetry bit rates. The telemetry pipeline now calls `ttc.telemetry_generation.calculate` directly; `main.py` creates the legacy hardware-sizing report separately, without feeding its results to downlink or OBDH.

**Only telemetry formula:** `rate_bps = sum(sensor_count * bits_per_sample / sampling_interval_s)` for fully specified channels. Operational events, packet overhead, mode duty cycles and time-tagging require separate explicit inputs; they are **not** inferred from subsystem power or mechanical equations.

**Shared PDF baseline:** Payload 100 bps and Structures 32 bps are *documented aggregate provisional rates*, used for Earth-link sizing until owners provide complete channel inventories. They are not independently calculated from sensors; the missing itemisation remains visible as 100 and 32 bps. For other subsystems, currently computed values are assumed inventories, not validated flight telemetry. Do not adjust sample sizes or cadences merely to reproduce a PDF total.

**Owner actions:** Provide for each monitored variable the sensor/channel count, quantisation bits, sampling cadence, operating mode and expected event bursts; clarify packet headers, compression, and whether payload PNT navigation broadcasts are separate from Earth-directed telemetry. Keep a documented source for every value. Re-run `main.py --telemetry-input <inventory.json>` to propagate changes to OBDH, DSN, downlink and Excel.

**Why the hardware report remains:** `outputs/subsystem_engineering.json` is retained for historical compatibility and cross-subsystem review only. Its EPS area and AOCS torque estimates are outside the TT&C data-generation scope and should not be presented as verified EPS/AOCS design outputs.

**Correction note:** Earlier documentation described 132 bps as an unitemised PDF fallback. This was replaced by a reverse-engineered channel model at the user's request; the inferred 12 bps Payload residual is still unresolved and must not be mistaken for verified hardware.
