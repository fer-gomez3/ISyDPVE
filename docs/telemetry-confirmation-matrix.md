# SELENA telemetry data budget — confirmation register

Source: `SUBSYSTEMS_Grupo_B_ISyDPVE.pdf`, 2 Nov 2026. Printed PDF section/page numbers below. All **ASSUMED_TBC** figures are engineering placeholders, not claims from the PDF.

## Already stated in PDF
- Payload §2.7.3 (p.14): **100 bps** continuous housekeeping to Earth via X-band, equivalent to **8.64 Mbit/day**.
- Structures §7.5.3 (p.52): **32 bps** mechanisms housekeeping, **2.7648 Mbit/day**. Includes 8 deployment switch bits, 2×16-bit SADM encoders, 2×16-bit HGA resolvers, 6 RTDs at 0.2 Hz.
- Payload §2.5.1 Table 4 (p.10): XD3 interface **4.32–43.20 Mbit/day**. This is NOT automatically additive to the 100-bps housekeeping figure; reconcile the meaning before using.
- Payload §2.5.1 Table 4 (p.10): AFS-I **250 bps net**, **21.60 Mbit/day** lunar surface broadcast, NOT Earth TT&C telemetry.
- Payload §2.5.1–2.7.3 (pp.10,14): XU3 ephemeris/clock uplink **0.10–1.00 Mbit/day**, Earth to satellite, NOT downlink telemetry.

## Working assumptions and confirmation requests
| Owner | Scenario value per satellite | Confirm with subsystem |
|---|---|---|
| Payload | 100 bps HK, 24 h max age assumed | Confirm HK payload format, XD3 4.32–43.20 Mbit/day interpretation, and any additional Earth-bound data; uplink packet sizes and cadence |
| Structures | 32 bps HK, 24 h max age assumed | Is 32 bps total including 6 RTDs at 0.2 Hz? Packet size/overhead, encoder and switch update rates, event burst on deployment |
| AOCS | 256 bps HK + 8 KiB/event weekly assumed | Star tracker/IMU/wheel telemetry channel count, sample sizes and logging cadence, maneuver/desaturation event sizes and frequency |
| EPS | 128 bps HK assumed | Number of V/I/SoC/DoD/MPPT/PCDU channels, quantization, sample cadence, events and fault logs |
| Thermal | 64 bps HK assumed | PT100/PT1000 count, bits per sample, sample cadence, heater status/command logging and anomaly burst |
| Propulsion | 32 bps HK + 16 KiB/event per 30 days assumed | Pressure/temperature/valve channels, sample cadence in idle/burn, maneuver log size and actual event frequency |
| OBDH | 128 bps HK/FDIR assumed | OBC health/FDIR logs, event bursts, compression, available storage per stream, retention policy and error-correction overhead |
| TT&C / Ground | Net rate **unknown** | X-band downlink net throughput, coding/modulation, packet/protocol overhead, link antenna G/T and pointing losses, acquisition time, DSN allocations, TX RF/DC/standby power |

## Distinctions
- Priority (criticality) and deadline (age/urgency) are provisional policy values, independent of data rate.
- Event traffic is represented by a **long-run average** for early sizing, not a guaranteed periodic maneuver schedule.
- No downlink rate or transmitter power is invented: the RF and energy models remain incomplete until their inputs are supplied.
- Historical 2020 contacts are **geometric opportunities only**, not a validated 2030 DSN schedule.
- The original `data/transfer_requirements.json` is preserved as a conservative PDF/TBD baseline. Use `--requirements data/transfer_requirements_scenario.json` for the explicit placeholder scenario.
