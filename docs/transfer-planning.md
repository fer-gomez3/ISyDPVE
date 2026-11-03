# Priorities, data volumes, DSN windows and power interfaces

Edit `data/transfer_requirements.json`. Run `python -m ttc.transfer_planning`.

**Input per subsystem**: `priority` 1..5; `mode` continuous (`rate_bps`) or event (`bytes_per_event` and `event_interval_hours`); optional `max_age_hours` overrides priority policy. Set missing values to `null`. For kilobytes or megabytes use bytes (1 kB = 1000 bytes; 1 MB = 1000000 bytes). Priority -> maximum tolerable data age is a *team planning policy*, not a physical law or a claim in the PDF. Defaults: priority 1/2/3/4/5 -> 168/72/24/12/6 hours. Hard mission requirement (e.g. one contact/24h) must be checked separately from stream priorities.

**Transfer math**: mean event rate = 8 * bytes/event / (3600 * hours/event). Required transfers/day = 24 / maximum age (a minimum *target*, not a guarantee). Data over epoch = mean bps * seconds. Given an independently assumed net downlink bps, minimum transmit time = data bits / (downlink bps * (1-overhead)). The downlink rate, overhead, setup and minimum contact come from `data/ttc_parameters.json`. Geometric contact windows are filtered by minimum duration and per-contact setup time; worst gap is evaluated. A station/satellite candidate schedule prevents overlap but is not a real antenna allocation and does not enforce realistic slews. Candidate geometry feasibility != operational DSN feasibility.

**Outputs**: `outputs/transfer_planning.json`, `transfer_by_subsystem.csv`, `transfer_contact_capacity.csv`. Station-level contact capacities are produced, but *per-subsystem per-station assigned time is intentionally null* until a validated stream-aware scheduler and DSN booking constraints are available. This avoids pretending a priority score establishes real allocated hours.

**EPS/TCS interface**: transmitter DC power, RF output and standby power are independent inputs from selected hardware or an RF link budget. `thermal_tx_heat_w_during_tx = dc_w - rf_w` is a simplified heat estimate; exclude RF output from heat only when emitted outside the spacecraft and account for other losses. `eps_tx_energy_wh_per_satellite_epoch` is calculated only if all telemetry rates, net downlink and transmitter DC are specified. Never infer W directly from MB or priority.

**Known inputs**: payload HK 100 bps and structures/mechanisms 32 bps, from the Subsystems PDF. Other sources remain unknown. The historical contact geometry uses 2020, not mission epoch 2030. The PNT S-band broadcast is separate from Earth DSN TT&C.
