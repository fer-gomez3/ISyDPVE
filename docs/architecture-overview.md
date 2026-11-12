# SELENA — Communication & Data Handling architecture

## Execution
From the repository root, run `python main.py` (or VS Code Run Python File while using the repository root as working directory).

Inputs:
- `data/transfer_requirements.json`: per-stream generation, urgency, recurrence and optional transmitter power.
- `data/contacts_master.csv`: historical geometric DSN visibility (2020; NOT the mission epoch).
- `data/link_budget_inputs.json`: independent **Earth TT&C** RF/hardware assumptions; all initially unknown.

Outputs in `outputs/`:
- `overview.json`: execution summary and missing inputs.
- `subsystem_interfaces.json`: PDF-based engineering reference; unknown rates remain null.
- `transfer_planning.json`, `transfer_by_subsystem.csv`, `transfer_contact_capacity.csv`: candidate geometry and transfer requirements.
- `power_budget.json`: RF link budget and EPS/TCS interface.

## Engineering chain
1. Subsystem telemetry streams: data rate (bits/s) or bytes/event and events/hour.
2. Urgency: independently assigned criticality and max acceptable data age.
3. Storage: accumulation rate and allocated buffer (stream-aware buffering still TODO).
4. Geometry: DSN contact opportunities; current heuristic is NOT a confirmed DSN schedule.
5. Scheduler: must eventually enforce storage, deadlines, station conflicts and finite downlink capacity.
6. RF: free-space path loss from distance and frequency, TX antenna gain, Earth station G/T, link losses, required Eb/N0, margin and bit rate.
7. EPS/TCS: if RF power and amplifier efficiency plus electronics consumption are known, calculate electrical power and dissipated heat; energy also requires a **real scheduled TX duration**.

## Model limits and provenance
- `null` means unprovided, not zero.
- A minimum calculated RF power is **not** a selected transmitter or verified mission link.
- PNT S-band navigation broadcast is a **different** link from Earth TT&C; never combine its 25 W RF with HGA TT&C without a validated system design.
- The original engineering and editable transfer planning modules are both exported, but their telemetry totals are not summed together.
- The power model does not automatically derive contact duration from the unvalidated candidate schedule. This avoids presenting hypothetical station time as confirmed EPS energy.
- Status `SCENARIO_LINK_CHECKED` means the algebra ran with supplied assumptions; it does not mean flight-qualified or DSN-approved.
- Future work: validated 2030 ephemerides, DSN resource allocations, link coding/modulation, pointing losses, hardware selection, shared buffer allocation, per-stream scheduler, test and integration verification.
