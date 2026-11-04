"""SELENA preliminary inputs transcribed from Subsystems PDF (66-page edition).

All data rates are NET INFORMATION rates, not symbol/chip rates.
Source: PDF pages 16-20, 32-36, 49, 50, 58-59 (PDF page numbering).
None of these entries represents a verified DSN X/Ka link design.
"""
from dataclasses import dataclass
from typing import Optional

SECONDS_PER_DAY = 86400

@dataclass(frozen=True)
class TelemetrySource:
    name: str
    rate_bps: Optional[float]
    source: str
    note: str = ""

TELEMETRY = (
    TelemetrySource("payload_housekeeping", 100.0, "PDF p.20, sec. 2.7.3", "8.64 Mbit/day; conflicts with broader XD3 range on p.16"),
    TelemetrySource("structures_mechanisms", 32.0, "PDF p.58, sec. 7.5.3"),
    TelemetrySource("aocs", None, "Not specified as net housekeeping rate in extracted inputs"),
    TelemetrySource("eps", None, "Not specified as net housekeeping rate in extracted inputs"),
    TelemetrySource("thermal", None, "Not specified as net housekeeping rate in extracted inputs"),
    TelemetrySource("propulsion", None, "Not specified as net housekeeping rate in extracted inputs"),
    TelemetrySource("obdh", None, "Not specified as net housekeeping rate in extracted inputs"),
)

# Separate service: lunar PNT broadcast is NOT automatically stored for DSN downlink.
PNT_BROADCAST = {
    "afs_i_net_bps": 250.0,
    "afs_i_daily_mbit": 21.60,
    "afs_q_information_bps": 0.0,
    "rf_output_w": 25.0,
    "payload_nominal_dc_w": 154.0,
    "source": "PDF pp.16-19, secs. 2.5-2.6",
}
TTNC_UPLINK = {
    "daily_min_mbit": 0.10,
    "daily_max_mbit": 1.00,
    "illustrative_net_bps": 2000.0,
    "source": "PDF pp.17,20, sec. 2.7.3",
}
PLATFORM = {
    "bus_voltage_v": 28.0,
    "nominal_total_w": 311.0,
    "peak_total_w": 336.0,
    "battery_wh": 1800.0,
    "dsn_obdh_mass_allocation_kg": 11.40,
    "structures_mechanisms_nominal_w": 5.2,
    "source": "PDF pp.32-36,58-59",
}
# Design parameters not yet defined by the source. Keep unknown, never silently zero.
DSN_LINK = {
    "downlink_net_bps": None,
    "tx_rf_power_w": None,
    "tx_dc_power_w": None,
    "tx_antenna_gain_dbi": None,
    "ground_station_g_over_t_db_per_k": None,
    "frequency_hz": None,
    "coding_margin_db": None,
}
