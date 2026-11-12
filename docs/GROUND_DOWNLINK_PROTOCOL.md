# SELENA — ground-coordinated downlink protocol, preliminary v0.1

**Scope:** requirements planning only. Not a DSN booking system, flight protocol, orbit propagator, or validated link budget.

## Roles and handshakes

1. Spacecraft OBDH reports per-stream backlog, generation timestamps, priority (1–5), delivery deadline and confirmation state.
2. SELENA mission operations computes requested windows and data volume using visibility predictions.
3. Ground segment provides **grants**: satellite, station, UTC start/end. Grants are external allocations; geometric visibility is not a booking.
4. Planner validates that each grant lies within a supplied visibility window, applies a configurable usable-time fraction, subtracts setup time, estimates required gross data rate including protocol overhead, and adds a design margin.
5. Operations sends a contact manifest (stream IDs, block sequence ranges, timestamps and expected sizes).
6. During contact, spacecraft prioritizes imminent deadlines, then higher priority, then FIFO. Ground reports received block ranges and missing blocks; unacknowledged critical blocks remain in OBDH storage for retransmission.
7. Contact closeout records delivered, unconfirmed, remaining and dropped volumes; next plan uses actual state.

**Important:** steps 5–7 are protocol requirements, NOT yet implemented in `ground_protocol_planner.py`. The current module performs step 4 and reports gap warnings, not packet-level delivery proof.

## Inputs

- `data/downlink_streams_example.json`: per-stream nominal bit rate, priority, maximum age (hours). Values are placeholders to be replaced by subsystem interfaces.
- `data/contacts_master.csv`: supplied candidate visibility. Currently historical 2020 data, NOT physically propagated 2030 geometry.
- `data/ground_grants_example.csv`: **illustrative**, externally supplied granted slots in the same epoch as visibility.
- `--utilization`: fraction of granted duration assumed usable before subtracting setup. Not evidence of DSN access.
- `--overhead`: fraction of gross bitrate used by protocol framing/control.
- `--design-margin`: fractional additional rate for sizing sensitivity.

## Run

```bash
python -m ttc.ground_protocol_planner
python -m unittest tests.test_ground_protocol_planner -v
```

Produces `outputs/ground_protocol_plan.json` with nominal required gross rate per grant, design peak and contact-cadence warnings.

## Required next integration

- Feed real 2030 propagated visibility and confirmed or assumed grants, with provenance.
- Generate explicit requests to ground segment, not just consume grants.
- Track actual per-stream backlog, due batches, ACK state, partial transfers, and interruptions; prove complete delivery by each deadline.
- Account for uplink, setup/acquisition/teardown, per-station resource conflicts, slew and station time caps consistently.
- Iterate rate, RF antenna gain/diameter, RF power, DC power, contact energy and memory capacity; reject physically infeasible designs.
- Add packet format and overhead model consistent with applicable CCSDS standards and project constraints.

## Implemented follow-up: deadline-aware fluid simulation

`ttc.ground_delivery.simulate` models per-stream backlog, priority tie-breaking,
oldest-bit deadlines and gross-rate capacity over the granted usable intervals.
`ttc.ground_delivery.size_rate` binary-searches a gross rate satisfying modeled
deadlines or returns `INFEASIBLE_WITH_GIVEN_GRANTS` if contact timing cannot
satisfy deadlines even at the configured upper rate. The CLI planner writes
`deadline_rate_sizing` alongside nominal contact demands.

This is **not** a packet/ACK implementation or a certified deadline guarantee:
generation is constant, reception perfect, and delivery is approximated in
discrete steps. The rate search uses a configurable finite upper bound.
The example grants are 2020-dated and cannot be treated as 2030 DSN allocations.

Run tests:
```bash
python -m pytest -q tests/test_ground_protocol_planner.py tests/test_ground_delivery.py
```

## Ground requests and application-level ACK prototype

`python -m ttc.ground_requests --gross-bps 256000` writes
`outputs/ground_contact_requests.json`. Each periodic request contains a
latest-finish deadline, requested grant duration, candidate station windows and
a `NO_SINGLE_WINDOW_LONG_ENOUGH` flag when necessary. These are **requests**,
not granted DSN time. Current request generation is a simple nominal single-window
baseline and does not optimize shared DSN resources.

`ttc.transfer_protocol.TransferSession` provides a Python-level block manifest
with satellite, subsystem, priority, deadline, length, SHA-256 checksum,
transmission status and selective acknowledgments. Unconfirmed blocks are
retained for retry; confirmed blocks can be released explicitly. This is **not**
a wire protocol, CCSDS CFDP implementation, or a verified end-to-end radio link.
The SHA-256 digest is a manifest integrity reference, not a replacement for
frame-level CRC/FEC or cryptographic authentication.

```bash
python -m pytest -q tests/test_ground_requests_transfer.py
```
