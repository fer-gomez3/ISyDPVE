# TODO for Claude and subsystem owners — reverse-engineered PDF telemetry

**Status: PLACEHOLDER — MUST BE REPLACED BY REAL SENSOR DATA.** These calculations intentionally reproduce published PDF aggregate rates using invented sampling/quantization choices. A match to a PDF number does **not** validate the underlying sensor model. Do not label these rates as physically derived or verified.

## Payload housekeeping: 100 bit/s (PDF §2.7.3)
The PDF identifies clock lock status, cell temperatures and SSPA RF power, and states **100 bit/s continuous HK**. It does not specify the complete channel inventory, bits per sample or cadences.

| Illustrative channel | Count | Bits/sample | Interval (s) | Rate (bit/s) |
| --- | ---: | ---: | ---: | ---: |
| Clock lock status | 1 | 8 | 1 | 8 |
| Clock cell temperatures | 4 | 16 | 1 | 64 |
| SSPA RF power | 1 | 16 | 1 | 16 |
| Payload health status **UNVERIFIED FILLER** | 3 | 4 | 1 | 12 |
| **Total** | | | | **100** |

The 3 health channels are not claimed to appear in the PDF. Confirm actual number of clock temperature sensors, whether RF-power monitoring includes more than one channel, bit quantization, sampling, time-tagging, packet headers, and the meaning of 'continuous'.

## Structures/mechanisms: 32 bit/s (PDF §7.5.3)
PDF identifies eight deployment microswitch bits, two 16-bit SADM encoders, two 16-bit HGA resolvers, and six RTD thermistors at 0.2 Hz. It gives **32 bit/s HK** but not every cadence or RTD bit depth.

| Channel | Count | Bits/sample | Interval (s) | Rate (bit/s) |
| --- | ---: | ---: | ---: | ---: |
| Deployment microswitch | 8 | 1 | **2 assumed** | 4 |
| SADM encoder | 2 | 16 | **4 assumed** | 8 |
| HGA resolver | 2 | 16 | **4 assumed** | 8 |
| Structural RTD | 6 | **10 assumed** | **5 documented** | 12 |
| **Total** | | | | **32** |

Do not interpret these intervals as flight requirements. Check whether microswitches are event-driven, whether deployment and HGA/SADM states are always sampled, whether the 32 bps is an aggregate *after* packetization, and whether temperature channels are shared with TCS.

## Claude implementation follow-up
1. Replace placeholder inventories with the actual payload and structures sensor lists from the owners; retain PDF totals only as reference values, not as computational overrides.
2. Add packet framing, time tags, event bursts, operating modes and compression **only when supported by defined inputs**. Avoid double-counting telemetry in OBDH and TT&C.
3. Ensure the Excel Telemetry tab uses the same channel equations as Python and shows a separate PDF reference, calculated total, delta, and **PENDING REAL DATA** label.
4. Verify `main.py` generates the seven streams from `telemetry_generation.json`, and that DSN/backlog/planning use these computed rates rather than stale values from `telemetry_detailed_scenario.json`.
5. Add tests that changing any channel's sampling interval changes both telemetry output and downstream transfer planning; test conservation of generated/downloaded/backlogged bits.
6. Add an explicit validation warning: matching a PDF aggregate via reverse engineering is *not independent verification*.
7. When real channels become available, do not force their sum to equal 100 or 32 bps. Report differences and investigate.

**Source distinction:** PDF §§2.7.3 and 7.5.3 supply aggregate rates and partial channel descriptions. The sensor bit allocations and periods shown in bold are engineering placeholders, not statements from the PDF.

## Review status (Claude follow-up)

| # | Item | Status |
| --- | --- | --- |
| 1 | Replace placeholder inventories with real sensor lists | **OPEN, needs the owners.** PDF totals are references only (not overrides) |
| 2 | Packet framing, time tags, bursts, modes, compression | **Not added**: no defined inputs. Protocol overhead is applied once, in the downlink model (`data/ttc_parameters.json`) |
| 3 | Excel Telemetry tab: same equations, PDF reference, difference, label | **Done**: formulas per channel, `PDF reference`, `Calculated - PDF`, `Status` with `PENDING REAL DATA` |
| 4 | Computed rates used by DSN/backlog/planning, not stale values | **Done**: `telemetry_detailed_scenario.json` no longer stores rates; `apply_computed_rates` is the single source; standalone `ttc.downlink_simulation` derives them from the inventories |
| 5 | Interval change propagates to telemetry and planning; conservation | **Done**: `tests/test_data_generation.py` (via `main.py --telemetry-input`) |
| 6 | Warning that matching a PDF aggregate is not independent verification | **Done**: `validation_status`, `validation_warning`, Excel status and technical report |
| 7 | Do not force sums to 100 or 32 | **Done**: the difference is reported, never forced |

Programming defects fixed in this review: (a) `telemetry_generation.calculate` still let the PDF aggregate override the channels, so the two entry points gave different rates for the same input; (b) a subsystem without inventory or reference was counted as 0 bit/s; (c) the source text of every subsystem was replaced by an origin code; (d) the number of satellites had a second source in `subsystem_engineering_inputs.json`.

The engineering decisions found in the review are in section 9 of `docs/technical-report.md`.
