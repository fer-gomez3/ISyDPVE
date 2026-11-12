"""Central shared parameters (downlink rate, DSN setup, contact policy).

Every module that needs one of these values reads it here, so no data file can contradict
another. Origins (documentation vs preliminary assumption) are stored with the values.
"""
import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data" / "ttc_parameters.json"


def validate(p):
    if int(p["n_satellites"]) < 1:
        raise ValueError("n_satellites must be >= 1")
    if float(p["downlink_gross_bps"]) <= 0:
        raise ValueError("downlink_gross_bps must be positive")
    if not 0 <= float(p["protocol_overhead_fraction"]) < 1:
        raise ValueError("protocol_overhead_fraction must be in [0, 1)")
    if float(p["dsn_setup_minutes"]) < 0:
        raise ValueError("dsn_setup_minutes must be nonnegative")
    if float(p["min_useful_tx_minutes"]) <= 0:
        raise ValueError("min_useful_tx_minutes must be positive: a contact must be able to carry data")
    if float(p["dsn_daily_network_hours"]) < 0:
        raise ValueError("dsn_daily_network_hours must be nonnegative")
    return p


def load(path=None):
    p = validate(json.loads(Path(path or DEFAULT_PATH).read_text(encoding="utf-8")))
    # The minimum contact always exceeds the setup time by the minimum useful transmit time.
    p["min_contact_minutes"] = float(p["dsn_setup_minutes"]) + float(p["min_useful_tx_minutes"])
    return p


def apply_policy(policy, params=None):
    """Return a copy of a module policy dict with the shared values overlaid (central wins)."""
    p = params or load()
    return {**policy,
            "net_downlink_bps": float(p["downlink_gross_bps"]),
            "protocol_overhead_fraction": float(p["protocol_overhead_fraction"]),
            "setup_minutes": float(p["dsn_setup_minutes"]),
            "min_contact_minutes": float(p["min_contact_minutes"]),
            "daily_network_hours": float(p["dsn_daily_network_hours"]),
            "daily_network_hours_sensitivity": list(p["dsn_daily_network_hours_sensitivity"]),
            "setup_minutes_sensitivity": list(p["dsn_setup_minutes_sensitivity"])}


def hga_link_defaults(antenna_path=None, params=None):
    """HGA-derived link fields: gain from the HGA definition, rate from the central parameters."""
    import math
    from .link_budget import C
    p = params or load()
    a = json.loads(Path(antenna_path or DEFAULT_PATH.parent / "hga_preliminary_design.json").read_text(encoding="utf-8"))
    d, eta, f = float(a["diameter_m"]), float(a["aperture_efficiency"]), float(a["frequency_hz"])
    gain = 10 * math.log10(eta * (math.pi * d * f / C) ** 2)
    return {"tx_gain_dbi": gain, "frequency_hz": f, "data_rate_bps": float(p["downlink_gross_bps"])}
