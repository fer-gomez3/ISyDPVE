# SELENA — TT&C / OBDH PDR preliminary engineering assessment

**Status:** Preliminary, traceable scenario assessment. **Not flight-validated.**
**Reference branch:** `feature/ttc-initial-structure`.
**Model epoch:** 2030-07-14T22:10:10.811Z, 96-hour scenario horizon.

## 1. Scope and architecture

Eight SELENA lunar navigation spacecraft generate platform housekeeping telemetry.
Earth TT&C/OBDH uses candidate DSN contacts (Madrid, Goldstone, Canberra).
The continuous lunar S-band PNT navigation broadcast is a **different service**
and is not automatically treated as stored Earth-directed housekeeping.
A lunar-surface-to-orbit relay is not in the documented C&DH baseline.

## 2. Telemetry generation

Two explicitly distinct data-generation profiles exist:

| Profile | Total per spacecraft | Interpretation |
|---|---:|---|
| Confirmed subtotal | 132 bit/s (11.4048 Mbit/day) | Payload housekeeping 100 bit/s + Structures 32 bit/s |
| Seven-stream scenario | 2301.74 bit/s (~198.87 Mbit/day) | Provisional channel inventories, assumptions and PDF aggregates; not independently confirmed |

Missing rates are not zero. The 100 bit/s payload housekeeping benchmark must
be reconciled with the separate payload XD3 volume range (4.32–43.2 Mbit/day).
The model excludes the 250 bit/s PNT broadcast from DSN telemetry.

## 3. DSN scheduling methodology

Both `ttc.dsn_pipeline` and `ttc.integrated_preliminary` call
`ttc.dsn_scheduler.schedule_contacts`. A full reserved contact includes
45 minutes of standard TT&C preparation, 10 minutes of acquisition and
15 minutes of teardown (70 minutes total), plus at least 5 minutes useful TX.
The operational timings are **planning assumptions**, not independently
verified NASA DSN requirements.

The scheduler enforces satellite/station non-overlap, geometric visibility,
shared UTC-day reservation budgets, minimum useful TX time, coverage feasibility,
priority/deadline awareness and equity. Coverage feasibility is checked on a
discrete time grid; the full schedule is **not** claimed globally optimal.

The 2020 visibility windows are reused as a calendar-shifted illustration
for 2030, **not** a 2030 orbital propagation or a DSN reservation.

## 4. Baseline results — reported validation on commit 4899695

| Scenario | Contacts | Satellites without contact | Reserved h | Delivered Mbit | Maximum peak buffer Mbit | Satellites violating deadlines |
|---|---:|---:|---:|---:|---:|---:|
| Historical 2020, previous allocator | 14 | SELENA_12, SELENA_13 | 139.6 | 3582 | 919 | 8/8 |
| Historical 2020, unified allocator | 9 | None | 14.9 | 3228 | 861 | 8/8 |
| Shifted 2030 96h, previous allocator | 6 | SELENA_11, SELENA_12 | 9.9 | 1592 | 795 | 8/8 |
| Shifted 2030 96h, unified allocator | 8 | None | 11.4 | 1492 | 748 | 8/8 |

These figures were reported from the previously executed
`python -m ttc.allocator_comparison` run; they have not been independently
rerun in this document-writing step. The old 2020 case did **not** enforce
the shared 3 h/day budget and is not a valid design baseline.

**PDR finding:** At the assumed shared 3 h/day reservation cap, all eight
spacecraft violate at least one telemetry delivery deadline. Coverage
alone does not demonstrate deadline compliance.

## 5. DSN sensitivity and requirement decision

Execute:

```bash
python -m ttc.dsn_sensitivity --hours 1 3 6 12 24
```

Generated: `outputs/dsn_sensitivity/sensitivity.csv`,
`sensitivity.json`, `deadline_sensitivity.png` (when matplotlib exists).

This sweep evaluates the assumed seven-stream telemetry profile using the
same scheduler, full reservation overhead and fixed 256 kbps gross downlink.
The first passing sampled budget, if any, is **not** a mathematically proven
minimum and is **not** a DSN allocation. AOCS/OBDH six-hour maximum-age
requirements must be approved by subsystem owners before they become
flight requirements. Changing deadlines to obtain a pass is not justified.

## 6. RF antenna sizing

The code evaluates free-space path loss, spacecraft antenna gain and pointing
loss, receiving G/T, required Eb/N0, margin and required RF/DC power.
Illustrative trade inputs include 8.4 GHz, 405000 km, 55% antenna efficiency,
0.15 degree pointing error, 45 dB/K receiver G/T, 6 dB Eb/N0, 4 dB losses,
3 dB margin and 35% amplifier efficiency. These are **unapproved scenario
assumptions**, not final equipment selection or demonstrated link closure.

The approved `data/link_budget_inputs.json` retains null fields for missing
RF design values. **No final HGA diameter, RF power or guaranteed margin
can be claimed** from these inputs alone.

## 7. EPS / thermal / OBDH interfaces

The integrated pipeline exports per-spacecraft contact and OBDH traces,
buffer and cumulative downlink PNG plots, a source comparison CSV and
electrical/thermal accounting interfaces. Component standby, TX, memory
interface and gimbal loads remain unknown in the hardware budget.
The report's OBC 25–30 W is an allocation reference, not a measured
complete TT&C load. The 11.4 kg TT&C+OBDH mass allocation is not a
derived hardware mass. No antenna mass is calculated.

Consequently nominal/peak electrical power, Wh/day and dissipated heat
cannot be closed without verified component draws and TX RF output.
The energy calculation deliberately returns null rather than inventing
zeros. A final EPS margin requires reconciliation with the latest spacecraft
EPS budget and prevention of Payload/OBC double-counting.

## 8. Open PDR actions and acceptance criteria

1. Obtain physically propagated 2030 spacecraft/ground-station visibility
   and confirm DSN resource assumptions and contact booking constraints.
2. Approve per-stream telemetry inventories and six-hour/other max-age
   requirements with AOCS, OBDH, EPS, TCS and Payload owners.
3. Execute the 1/3/6/12/24 h/day sensitivity and choose a resource/reliability
   concept; report any unresolved deadline violations.
4. Approve X/Ka hardware frequencies, EIRP/antenna pointing, station G/T,
   coding Eb/N0, RF power cap and all relevant losses.
5. Approve standby/RX/TX/gimbal/memory DC loads, RF efficiency, thermal
   dissipation and daily duty cycles. Check against the EPS allocation.
6. Replace provisional 2020 visibility and illustrative link assumptions
   before claiming mission compliance.

**Engineering disposition:** A functioning, testable preliminary
communications/OBDH analysis is ready for PDR discussion. Requirements
compliance and final hardware budgets remain **OPEN**.
