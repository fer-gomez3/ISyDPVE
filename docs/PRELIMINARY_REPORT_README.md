# SELENA — preliminary TT&C report workflow

## One command

```bash
python -m ttc.integrated_preliminary
```

This runs the existing adaptive-storage baseline and then uses **the same**
telemetry generation requirements, calendar-shifted visibility and simulated
allocated contacts for an integrated ground-contact request, deadline/rate,
RF/EPS/TCS sensitivity assessment.

## Outputs

- `outputs/SELENA_integrated_preliminary_report.md`: report-ready summary
- `outputs/integrated_preliminary.json`: traceable full scenario, requests,
  grants, rate, deadline and link inputs/results
- `outputs/integrated_satellite_summary.csv`: per-satellite data and violations
- `outputs/integrated_contact_requests.csv`: requests, candidate counts and
  unmet windows
- `outputs/rf_trade_study.csv` and `.json`: antenna diameter vs RF power,
  DC power, thermal dissipation and energy per contact
- Existing `outputs/SELENA_preliminary_report.md`, OBDH and hardware trades

## Interpretation

The 2030 geometry is NOT propagated: 2020 windows are calendar-shifted.
The DSN contacts are hypothetical allocations; there is no confirmed DSN
reservation or demonstrated station service availability. Rates, generation,
pointing error, DSN G/T, required Eb/N0, losses, antenna efficiencies and
transmitter efficiencies are scenario inputs and must be checked against
approved requirements and actual provider capabilities. The RF sensitivity
config is explicitly illustrative.

`ground_delivery` assumes perfect reception and continuous fluid-bit traffic.
It is NOT integrated with the separate selective-ACK prototype and does not
provide packet-level verified delivery or a flight CCSDS stack. The existing
`adaptive_storage` simulates event bursts and memory constraints independently;
the integrated deadline simulation uses constant mean rates instead, so its
memory and deadline outcomes must not be presented as a single validated
end-to-end burst-aware result.

The study is **preliminary engineering**, not final design closure.
For PDR closure obtain the real orbit ephemerides, station visibility,
availability/grants, approved subsystem telemetry ICDs, selected coding and
modulation, verified DSN station G/T and RF loss budget, and qualified hardware
mass/power/pointing limits. Do not replace missing evidence with invented data.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Replacing illustrative visibility/grants

`ttc.integrated_preliminary.run(visibility_path="path/to/2030_visibility.csv", grants_path="path/to/ground_grants.csv")`
accepts explicit station/satellite UTC intervals with columns
`satellite,station,start_utc,end_utc`. The pipeline validates interval
coverage and station conflicts through the delivery planner. A supplied file
is not proof of propagation or booking: retain source/provenance records.
Both external inputs should be supplied together; otherwise synthetic
baseline allocations can conflict with real geometry. The existing
adaptive-storage baseline remains a separate illustrative scenario and must
not be conflated with external-grant results.

## RF/EPS/TCS sensitivity

`python -m ttc.rf_trade_study` computes gain, beamwidth, pointing loss,
required RF power, electrical DC load, dissipated heat and contact energy
across candidate antenna diameters. All numbers in
`data/rf_trade_assumptions.json` are **illustrative placeholders**,
not approved DSN G/T or selected hardware. The required Eb/N0 is a
placeholder until modulation, coding and BER/FER are agreed.
