# SELENA TT&C + OBDH preliminary model: technical report

Version: final consolidated model for `feature/ttc-initial-structure`. Scope: Earth telemetry/command link and on-board data handling of the 8-satellite SELENA lunar PNT constellation. The lunar PNT broadcast (AFS, S-band) is a separate service and is not sized here.

## 1. Status legend

Every value in the model carries one of four statuses. The workbook colours them (green, yellow, blue, red).

| Status | Meaning | Examples |
|---|---|---|
| **DOC** | Taken from the project documentation | 8 satellites; payload housekeeping 100 bps (PDF 2.7.3, provisional); structures 32 bps (PDF 7.5.3); TT&C + OBDH mass allocation 11.40 kg; HGA gimbal counted in Structures |
| **ASSUMPTION** | Preliminary engineering assumption, not verified | HGA 0.38 m, aperture efficiency 0.6, 8.4 GHz; downlink 256 kbps; protocol overhead 20 %; DSN preparation 45 min + acquisition 10 min and teardown 15 min per contact (standard TT&C policy, user-supplied, unverified; the former 15 min setup is a legacy sensitivity); minimum useful transmit 5 min; 3 h/day of DSN time for all satellites; ADCS/EPS/thermal/propulsion/OBDH sensor inventories; data-age deadlines per priority |
| **CALC** | Calculated by the model from the values above | Telemetry rates, HGA gain, capacity, allocation, backlog |
| **INPUT NEEDED** | Missing, prevents final validation | Distance from real geometry, DSN G/T, required Eb/N0, losses, margin, PA efficiency, transponder power |

Shared parameters (downlink rate, overhead, setup, minimum contact, DSN hours, number of satellites) live only in `data/ttc_parameters.json`; `ttc/parameters.py` overlays them everywhere, so no data file can contradict another. The minimum contact is always `setup + minimum useful transmit` (20 min), so every contact can carry data.

## 2. Architecture

```
data/*.json, data/contacts_master.csv
        |
main.py -> telemetry_generation -> transfer_planning / downlink_simulation
        |-> hga_sizing -> link_budget -> power_budget
        |-> dsn_allocation (fair) -> downlink_simulation -> satellite_outputs
        |-> xband_trade_study, dsn_access_sensitivity, contact_energy_optimizer
        '-> export_workbook  ->  outputs/SELENA_TTC_Model.xlsx
```

Contact windows enter as `data/contacts_master.csv` (`contact_id, station, satellite, start_utc, end_utc`). By default the historical 2020 windows are shifted to the 2030 epoch (`ttc/shift_contact_epoch.py`): this is a **hypothetical scenario, not orbit propagation**. To use real ephemeris-derived windows, provide a CSV of the same format and run `python main.py --contacts <file> --no-epoch-shift`. Raw ephemerides are described in `ttc/ephemeris_format.md`.

## 3. Equations

**Telemetry.** Component rate = `count x bits per sample / interval`. Subsystem rate = sum of its components, or the documented aggregate. Daily volume = `rate x 86400` (Mbit/day) and `/8e6` (MB/day, decimal).

**HGA.** `lambda = c/f`, `G = eta (pi D / lambda)^2`, `G_dBi = 10 log10 G`, half-power beamwidth ~ `70 lambda / D`.

**Link budget (downlink).**
`FSPL = 20 log10(4 pi d f / c)`
`EIRP_req = Eb/N0_req + margin + 10 log10(R) + FSPL + L_other - G/T + 10 log10(k)` (k = 1.380649e-23 J/K; the Python engine uses the rounded constant -228.6 dBW/K/Hz, a 0.0008 dB difference)
`P_RF,min = 10^((EIRP_req - G_tx)/10)`; achieved margin for a chosen RF power `P`: `10 log10(P/P_RF,min) + margin`.

**Power.** `P_DC = P_RF / eta_PA + P_electronics`, heat `= P_DC - P_RF`, transmit energy per day `= P_DC x transmit time`.

**Capacity and DSN time.** Net rate `= R_gross (1 - overhead)`. Transmit time per satellite per day (one contact) `= daily data / net rate`; contact time adds the setup time. DSN time for all satellites `= N x (transmit + setup)`. Required net rate to fit one contact per satellite per day in the assumed DSN hours: `daily data / (hours x 60 / N - setup) / 60`.

**DSN allocation (`ttc/dsn_allocation.py`).** Candidate segments come from the geometric windows with one antenna per station and one link per satellite. Each UTC day, the assumed network hours are shared by all satellites with max-min fairness: the satellite with the least assigned time is served next (new contact = minimum contact, then one-minute increments, preferring an already started contact). A satellite with no usable segment gets nothing, no contact is created, setup counts against the cap, and no service is guaranteed.

**Backlog simulation (`ttc/downlink_simulation.py`).** This is a **time-discretized approximation** (60 s steps). Each stream generates at a constant mean rate and is delivered FIFO. Outside a contact, and during setup, data only accumulates. During the useful part of a contact the simulation advances in 60 s steps: data generated in the step joins the backlog and the step capacity (`net rate x step`) is spent in priority order, so data generated during a contact is transmitted when capacity allows. The age of the oldest undelivered bit is exactly `backlog / generation rate`; a stream is flagged when it ever exceeds its maximum data age. Ages are evaluated at step boundaries, so a maximum age can be underestimated by up to one step. Sensitivity to the step was checked on the full scenario with steps of 60, 30, 10 and 1 s: downloaded volumes are identical, the sets of streams at deadline risk are identical, and the maximum data age differs from the 1 s run by at most 0.016 h (about 1 min) at 60 s.

## 4. Results

All results are for the **hypothetical shifted scenario** (2030-07-14 22:25 UTC to 2030-07-19 07:42 UTC, 4.4 days) and the assumptions of section 1.

### 4.1 Telemetry (per satellite)

| Subsystem | Rate (bit/s) | Mbit/day | Status |
|---|---|---|---|
| Payload housekeeping (PDF 2.7.3 aggregate; itemised 0, unitemised remainder 100) | 100 | 8.64 | DOC aggregate, PROVISIONAL; no documented channel is complete |
| Structures (PDF 7.5.3 aggregate; itemised 0, unitemised remainder 32) | 32 | 2.77 | DOC aggregate, PROVISIONAL; cadences and RTD bit depth missing |
| ADCS (31 ch x 32 bit / 0.625 s) | 1587.2 | 137.13 | ASSUMPTION |
| Propulsion (12 x 16 bit / 5 s) | 38.4 | 3.32 | ASSUMPTION |
| EPS (22 x 32 bit / 5 s) | 140.8 | 12.17 | ASSUMPTION |
| Thermal (30 x 16 bit / 5 s) | 96 | 8.29 | ASSUMPTION |
| OBDH (12 x 32 bit / 1.25 s + 1024 bit / 7200 s) | 307.34 | 26.55 | ASSUMPTION |
| **Total** | **2301.74** | **198.87** (24.86 MB/day; 198.87 MB/day for 8 satellites) | CALC |

ADCS is 69 % of the volume and rests entirely on an assumed channel inventory. Payload and Structures use the documented aggregates (100 and 32 bit/s) as a provisional TT&C sizing value. The documented channels are listed but none has count, bits and cadence together, so the itemised rate is 0 and the **unitemised remainder** is 100 and 32 bit/s (132 bit/s in total, 5.7 % of 2301.74). Nothing was invented or adjusted to reach those values; when the owners supply the missing numbers the itemised part grows and the remainder shrinks, and a difference from the PDF is reported, not forced. See `docs/subsystem-data-provenance.md`. The telemetry rates come only from the channel inventories; the engineering equations (EPS, AOCS, propulsion, thermal, structures, OBDH) size hardware and do not determine them.

The satellite-to-Earth calculations read `outputs/data_generation_interface.csv/json`: per subsystem the rate, bits/day, mode, priority, maximum data age, origin (DOC / ASSUMPTION / INPUT NEEDED), PDF reference, difference and validation status, plus totals per spacecraft and for the constellation.

### 4.2 HGA and downlink (380 mm, 256 kbps)

- Idealized gain **28.27 dBi** (eta 0.6, assumed), half-power beamwidth 6.6 deg, link duty cycle needed 1.1 % of the 204.8 kbps net rate.
- Minimum RF power for 256 kbps with the assumed Eb/N0 10 dB, margin 3 dB and other losses 3 dB (total, RF-only; DC power adds PA efficiency and electronics, both assumed 0.4 and 5 W in the trade study). **DSN G/T is an assumption**:

| Distance (km) | G/T 25 dB/K | 30 | 40 | 50 |
|---|---|---|---|---|
| 384 400 | 12.14 W | 3.84 W | 0.38 W | 0.04 W |
| 400 000 | 13.15 W | 4.16 W | 0.42 W | 0.04 W |
| 420 000 | 14.49 W | 4.58 W | 0.46 W | 0.05 W |

These figures are conditional, not a feasibility conclusion: the DSN G/T, required Eb/N0, other losses, margin and distance are unverified assumptions, so the link is **not** considered validated until those inputs are confirmed. The RF power depends mostly on the DSN G/T and the required Eb/N0.
- The trade scenario also contains 20 to 35 dBi gain cases. A 33 dBi antenna would need about 0.655 m at eta 0.6, so it is inconsistent with the 0.38 m baseline and is shown only as a trade case.

### 4.3 DSN time and data volume (the main finding)

With the assumed 15 min setup, **one contact per satellite per day does not fit in the assumed 3 h/day of DSN time**:

| Quantity | Value |
|---|---|
| Transmit time per satellite per day at 204.8 kbps net | 16.2 min |
| Contact time incl. 15 min setup | 31.2 min |
| DSN time, 8 satellites, one contact per day each | **4.16 h/day (assumption: 3 h/day)** |
| Net / gross rate needed to fit in 3 h/day | 442 kbps / 552 kbps |
| Contacts per day to meet the tightest assumed deadline (OBDH, 6 h) | 4 per satellite, 10.2 h/day of DSN time |

Under the sensitivity of `dsn_access_sensitivity.json` (useful hours in the epoch): 3 h/day with 5, 15, 30 min setup gives 15.4, 10.3, 5.0 h.

### 4.3.1 Proposed four-contact DSN reservation plan (MAR-based planning case)

The **SELENA Mission Analysis Report (MAR), Section 7.5.1 (Global Coverage)** states that each spacecraft has **more than 8.5 h/day (510 min/day)** of geometric visibility with a single DSN antenna, using a ground-station elevation mask of at least 10°. This is a geometric lower bound, **not a guaranteed DSN booking or four distinct passes**.

For preliminary TT&C operations, a separate **four contacts per spacecraft per day** planning case is proposed. Each nominal contact comprises 16.8 min of effective transmission and 7.2 min of operational overhead. A further 1.5 min per contact is reserved as a scheduling contingency to obtain a rounded planning allocation of 20% of the MAR minimum visibility.

| Parameter | Per contact | Per spacecraft / day | Eight-spacecraft constellation / day |
|---|---:|---:|---:|
| Number of contacts | 1 | 4 | 32 |
| Operational overhead* | 7.2 min | 28.8 min | 230.4 min |
| Effective transmission | 16.8 min | 67.2 min | 537.6 min |
| **Nominal contact duration** | **24 min** | **96 min** | **768 min (12.8 antenna-h)** |
| Scheduling contingency | 1.5 min | 6 min | 48 min |
| **Target DSN reservation** | **25.5 min** | **102 min** | **816 min (13.6 antenna-h)** |
| MAR minimum geometric visibility | — | > 510 min | Not additive as shared station availability |
| **Target fraction of MAR minimum visibility** | — | **20%** | **20% per spacecraft** |

*Operational overhead comprises preparation (2.4 min), acquisition (2.4 min) and closure (2.4 min) per contact. The additional 1.5 min is contingency time, not additional nominal transmit time.*

Calculations: `4 × 25.5 = 102 min/day/spacecraft`; `102 / 510 = 20%`; `8 × 102 = 816 min/day = 13.6 antenna-h/day`. The nominal fraction without contingency is `96 / 510 = 18.82%`; the extra 6 min/day is a **6.25% margin relative to the nominal 96-min reservation**. Since MAR visibility **exceeds** 510 min, 20% is a rounded **upper bound on the required fraction of actual daily geometric visibility**, provided the four reservations can be placed within it.

**Scheduling and subsystem constraints.** Each entire 25.5-min reservation (including overhead and contingency) must lie within an actual geometric visibility interval; station/antenna and spacecraft reservations must not overlap, and contacts must be distributed appropriately to satisfy telemetry-age requirements. The MAR daily visibility aggregate alone cannot establish four schedulable slots or a station-by-station allocation. The 13.6 antenna-h/day requirement is **incompatible with the existing hypothetical 3 h/day shared DSN cap** and therefore represents a *requested planning capacity*, not the current allocator output or a confirmed NASA/JPL allocation. The 2.4/2.4/2.4-min phases are **new preliminary operational assumptions**, different from the legacy 45/10/15-min policy and 15-min simplified setup used elsewhere in this report and in current code. **Do not treat this new case as implemented or verified by the scheduler until its inputs and tests are reconciled.** RF data rate, antenna sizing, EPS and Thermal hardware parameters remain unchanged; compatibility of the longer reservation duty cycle with power and thermal limits still requires verification.

### 4.4 Scenario allocation and backlog (3 h/day shared fairly)

140 candidate segments, 31 eligible contacts, 18.0 h assigned, 10.25 h of useful transmit time. The 18.0 h is 3 h on each of **six UTC calendar days** (14 to 19 July 2030): the daily cap applies per calendar day, and the first and last days are partial, so the simulated period is only about 4.4 days and the assigned hours are not proportional to its duration. All eight satellites receive time; the differences come from contact availability in the input windows, not from priority.

| Satellite | Candidate h | Assigned h | Useful TX h | Contacts | Generated Mbit | Downloaded Mbit | Remaining Mbit | Worst stream (max age / deadline, h) |
|---|---|---|---|---|---|---|---|---|
| SELENA_11 | 17.0 | 1.47 | 0.72 | 3 | 918.8 | 376.2 | 542.7 | obdh_hk_logs (57 / 6) |
| SELENA_12 | 19.5 | 1.97 | 0.97 | 4 | 918.8 | 525.0 | 393.8 | propulsion_hk (80 / 12) |
| SELENA_13 | 21.1 | 2.93 | 1.93 | 4 | 918.8 | 874.5 | 44.3 | propulsion_hk (103 / 12) |
| SELENA_21 | 16.1 | 2.37 | 1.37 | 4 | 918.8 | 462.9 | 455.9 | propulsion_hk (110 / 12) |
| SELENA_22 | 15.0 | 1.53 | 0.78 | 3 | 918.8 | 445.2 | 473.7 | obdh_hk_logs (57 / 6) |
| SELENA_23 | 17.7 | 2.47 | 1.47 | 4 | 918.8 | 844.2 | 74.7 | propulsion_hk (95 / 12) |
| SELENA_31 | 17.9 | 2.93 | 1.68 | 5 | 918.8 | 844.2 | 74.7 | propulsion_hk (75 / 12) |
| SELENA_32 | 17.5 | 2.33 | 1.33 | 4 | 918.8 | 451.4 | 467.4 | propulsion_hk (108 / 12) |

Data volume is conserved for every satellite (generated = downloaded + remaining), and the downloaded totals agree with an independent aggregate model. Satellites 13, 23 and 31 download more than 90 % of their data; the other five download 40 to 57 %. Their average useful transmit time (0.7 to 1.4 h over the 4.4 days) is of the order of the 16.2 min per day needed, but it is split into few contacts, days apart, and what remains was generated after each satellite's last contact in the window. Every satellite also exceeds the assumed data-age deadlines (the table shows the worst stream), because the gaps between candidate windows in the shifted scenario are days long and each contact first loses 15 min to setup. These results depend on the assumed setup time, DSN hours and placeholder geometry; they are not a property of the link itself and must not be read as a validated schedule.

## 5. Verification performed

| Area | Method | Result |
|---|---|---|
| Telemetry | Recomputed from the sensor inputs | 2301.7422 bit/s, 198.87 Mbit/day, matches |
| HGA gain | Closed form | 28.2694 dBi |
| Link budget | 180 trade cases recomputed independently with the exact Boltzmann constant | Maximum relative difference 1.9e-4 (rounded constant) |
| Power | `P_DC`, heat, energy recomputed; workbook recalculated in LibreOffice | Python and workbook agree to 2e-4 |
| DSN allocation | Invariants: daily cap, minimum contact, useful = assigned - setup, all 8 satellites served, no invented contacts | Pass |
| Storage | Independent aggregate backlog model; conservation of data | Pass |
| Sensitivity | Sensors, antenna diameter, RF power, data rate, setup, DSN hours; workbook recalculation after input changes | Propagates as expected (`tests/test_sensitivity.py`) |
| Environment | Clean Python 3.11 and 3.12 environments; GitHub Actions on 3.11 and 3.12 | See the delivery report |

## 6. Limitations

- Contact geometry is the historical 2020 data shifted to 2030; it is **not** orbital propagation and not valid for that date. Range and elevation are not derived from it.
- No DSN reservation exists. The 3 h/day, 15 min setup and 5 min minimum useful time are assumptions.
- Eb/N0, coding, modulation, implementation loss, atmospheric attenuation by elevation, lunar occultation, Sun noise and pointing losses are not modelled beyond a single assumed loss and margin.
- The 7.2 GHz uplink is not checked. Command and tracking (ranging) data volumes are not included.
- Event bursts (propulsion burns, anomalies) and OBDH storage margins are not modelled; the onboard buffer is reported as peak backlog only.
- The idealized HGA gain assumes a circular aperture and efficiency 0.6; it is not a manufacturer value.

## 7. Engineering inputs still required

| From | Input |
|---|---|
| ADCS | Real telemetry channel list, sample size and rates; event data |
| EPS | Housekeeping channels; bus power available for TT&C during transmission |
| Thermal | Sensor count, sample size and rate; allowable dissipation of the TT&C equipment |
| Propulsion | Housekeeping channels; burn/event data volume and timing |
| Structures | HGA pointing mechanism mass and power (currently 1.5 kg, 2 W placeholders) and pointing accuracy |
| Payload | Confirmation of 100 bps housekeeping (the PDF also gives a broader range) |
| Orbit / mission analysis | Ephemerides of the 8 satellites for 14 July 2030 22:10:10.811 UTC; resulting contact windows, ranges, elevations |
| Ground segment | Real DSN allocation, setup time, G/T of the antennas, uplink/downlink frequencies |
| TT&C hardware | Modulation, coding and required Eb/N0; PA efficiency; transponder power; losses; selected HGA and its measured gain and mass |
| OBDH | Memory technology, margins and storage policy |

## 8. Changes in the final version

- Formula-based Excel workbook (`ttc/export_workbook.py`); empty link/power sheets show `INPUT NEEDED`; Checks sheet reconciles workbook and Python.
- Centralised shared parameters; setup 15 min; minimum contact exceeds setup (validated).
- Fair daily DSN allocation for all satellites.
- Backlog simulation transmits data generated during a contact; deadline check uses the exact age of the oldest bit.
- HGA gain, frequency and rate wired into the link budget, power budget and contact-energy ranking (the 33 dBi placeholder was removed).
- Per-satellite JSON/CSV outputs; X-band trade study includes the HGA baseline gain.
- Data-generation review: one telemetry code path (channels win, PDF aggregate is only a reference or fallback), a subsystem without inventory is `MISSING_INPUT` instead of 0 bit/s, stream rates are never stored in `telemetry_detailed_scenario.json`, the number of satellites has one source, `--telemetry-input` for what-if runs, and the Excel Telemetry tab shows PDF reference, difference and `PENDING REAL DATA`.
- Earlier fixes: transfer-stream names matched to the generated telemetry; power-budget margin test; `--output-dir` honoured by the workbook; `--no-epoch-shift` option added.

## 9. Review of the subsystem engineering models: open engineering decisions

Not applied; they change engineering assumptions and need your decision.

| # | Observation | Proposal |
|---|---|---|
| 1 | Payload/Structures: decided (unitemised remainder), implemented | Owners supply channel counts, bits and cadences |
| 2 | EPS: decided and implemented, single lecture route A = P_sa / P_EOL, area 0.917 m^2 (earlier fitted route 1.466 m^2). `cell_specific_power_w_m2` = 500 is unchanged and unjustified (about 37 % efficiency at 1361 W/m^2) | EPS owner to confirm; PDF 410 W array and 1800 Wh battery are shown as references with differences (-22.2 W, -2.1 Wh) |
| 3 | EPS eclipse hours (6.5068) reproduce the documented 1.8 kWh battery, which also looks tuned | Replace with the eclipse duration from the orbit analysis |
| 4 | AOCS: implemented r(nu) = a(1-e^2)/(1+e cos nu), torque at periapsis, apoapsis and orbit average; wheel requirement = (slew + gravity gradient) x margin, max-only shown for comparison. The repo has no periapsis/apoapsis, so the result uses 6200 km as a circular lower bound (`CIRCULAR_RADIUS_LOWER_BOUND_PERIAPSIS_INPUT_NEEDED`); torque scales with (r_apo/r_peri)^3 | Mission analysis to supply periapsis/apoapsis (the same orbit as the EPS eclipse hours); other disturbances still missing |
| 5 | No equation links hardware sizing to the number of telemetry channels | Request real channel lists from each owner (section 7) |
