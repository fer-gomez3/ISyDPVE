# SELENA Communications — Master checklist

Updated 2026-11-09. **Do not check an item until its calculation, provenance, and tests are reviewed.** Scope: communications only; avoid double-counting OBDH, ADCS, and Payload EPS loads.

## 1. Overview and requirements
- [x] Audit current telemetry, scheduling, link and RF-trade modules (initial code audit).
- [ ] Recover existing antenna diameter/configuration from Payload report; **mass and hardware selection are handled by user**.
- [ ] Establish authoritative inputs and provenance; remove contradictions between legacy 15-min setup and 70-min full-contact overhead.
- [ ] Verify station G/T, coding, frequency, losses, antenna efficiency and receiver requirements.

## 2. Data flows
- [ ] Validate each subsystem's channel counts, bits/sample, cadence and event bursts against owner ICDs (existing figures provisional).
- [ ] Model rover/lunar terminal -> spacecraft data rate, traffic profile, RF reception and storage.
- [ ] Reconcile adaptive and integrated telemetry generation (burst versus constant mean).
- [ ] Calculate spacecraft -> Earth gross/net rate, grant overhead, memory backlog and deadlines using one shared scenario.
- [ ] Replace 2020 calendar-shifted contact windows with propagated 2030 visibility and separately verified station allocations.
- [ ] Validate protocol overhead, error/retransmission behavior and packet-level transfer assumptions.

## 3. Antenna diameter sizing (NO mass prediction)
- [x] Initial research on existing antennas (reference only; user will select mass/hardware).
- [ ] Build traceable same-technology diameter/area–mass dataset; separate patch arrays from reflectors.
- [ ] Fit/compare m(D)=a D^b and areal-density model with uncertainty, holdout checks, and no unsupported extrapolation.
- [ ] Add feed, mount, two-axis gimbal, cabling and mechanism mass; avoid double-counting structure.
- [x] Implement Earth link diameter-grid sensitivity (illustrative assumptions; not validated).\n- [ ] Verify Earth and lunar link budgets across antenna options and required rate, including beamwidth and pointing.
- [ ] Recommend a diameter based on link closure and available RF power; user maps diameter to actual antenna hardware/mass.

## 4. Communications electrical budget
- [ ] TX RF, PA efficiency, electronics, standby and thermal dissipation.
- [ ] Lunar RF receiver, LNA, demodulation and interface power.
- [ ] OBDH communication-attributable processing/memory power without double-counting.
- [ ] Two-axis pointing: acquisition/slew, tracking and idle power with duty cycles.
- [x] Implement mode accounting for OFF, standby, lunar RX, Earth TX, slew and simultaneous RX+TX (incomplete hardware inputs remain null).\n- [ ] Validate component powers and duty-cycle modes with owners.
- [ ] Peak/average W, energy Wh/contact and Wh/day, per spacecraft and constellation, with margins.

## 5. Verification and deliverables
- [ ] Integrate common inputs and outputs into one reproducible pipeline.
- [x] Add initial mode accounting and RF-grid unit tests (CI result to verify).\n- [ ] Expand tests: zero traffic, no contact, loss of visibility, no RF closure, high duty cycle and conservation.
- [ ] Sensitivity sweeps: 15/30/45 cm, G/T, bit rate, pointing error, efficiency, mass assumptions, ground hours.
- [ ] Independent hand calculations and numerical cross-checks.
- [ ] Payload interface: recommended diameter, RF performance, pointing and assumptions; user selects hardware/mass.
- [ ] EPS interface: W by mode, W peak/mean, Wh/day and uncertainty (currently null until owner inputs).
- [ ] PDR communications chapter with plots, sources, constraints and unresolved requirements.

## Initial sourced antenna references (NOT interchangeable mass-vs-diameter calibration points)
| Product | Type | Aperture/envelope | Mass | Gain | Source |
|---|---|---|---|---|---|
| AAC Clyde PULSAR-XANT-PLUS | patch | 43×43 mm | 8 g | 12 dBi | https://www.aac-clyde.space/what-we-do/space-products-components/communications/pulsar-xant-plus |
| Anteral X-band SCP | patch | 99×99 mm | 127 g | 19 dBi directivity | https://anteral.com/products/high-gain-x-band-scp/ |
| ANYWAVES X-band telemetry | patch | 72.6×72.6 mm | 59±3 g | 11.5 dBi | https://satcatalog.s3.amazonaws.com/components/1303/SatCatalog_-_Anywaves_-_X-Band_Payload_Telemetry_Antenna_-_Datasheet.pdf |
| INRASE X-band | antenna assembly | 100×200 mm | 130 g | 18.5 dB | https://inrase.com/ |

**Engineering warning:** These are different technologies/envelopes and cannot justify a universal reflector mass–diameter law. No verified mass for the existing 15/30/45 cm SELENA reflector candidates, gimbal or feed is available. A mass estimate from those four samples would be misleading.

## Verified current code behavior
- RF sensitivity at 8.4 GHz and 256 kbps: 15/30/45 cm, with illustrative G/T 45 dB/K, 55% efficiency, 35% PA efficiency and 8 W electronics.
- Integrated RF closure file still has nulls and returns MISSING_INPUTS.
- 2030 contact geometry is synthetic, deadlines not met in last CI.
- TX-only 8.34 W at 30 cm is **not** complete communications power.
- The model does not yet compute RX lunar, gimbal electrical loads, total communications modes, or mass of antenna assembly.

## Iteration protocol
1. Run existing tests and record commit SHA.
2. Implement one subsystem/model change and its tests.
3. Run nominal and corner-case tests; check physical units and energy conservation.
4. Compare against independent calculation and source specification.
5. Record outputs, unresolved assumptions, and update checkboxes only when verified.
\n## Implementation iteration 1 — 2026-11-09\n- Added `ttc/communications_budget.py`: RF diameter sweep with link requirements and optional RF power cap; explicit missing-data status. No antenna mass model.\n- Added `data/communications_budget_inputs.json`: 15/30/45 cm; current 30 cm; illustrative Earth downlink RF values; RX/OBDH/gimbal power inputs null.\n- Added `tests/test_communications_budget.py`: power accounting, missing-data propagation, monotonic diameter sensitivity and simultaneous-mode shared-load check.\n- Run: `python -m unittest discover -s tests -v` and `python -m ttc.communications_budget`.\n- **Unresolved:** rover link RF, component power specs, duty cycle, 2030 physical geometry, station allocation and final diameter selection.\n