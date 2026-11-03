"""Formula-driven preliminary subsystem engineering and telemetry interfaces.

Lecture equations are engineering sizing relationships, NOT telemetry-rate laws.
Channel counts, quantization and sampling periods are explicitly hypothetical.
All outputs are PER SPACECRAFT; lunar PNT broadcast is excluded.
"""
import json
import math
from pathlib import Path
from .parameters import load as load_parameters

DAY = 86400
G0 = 9.80665
SIGMA = 5.670374419e-8

def channel_rate(ch):
    n, b, dt = ch["count"], ch["bits_per_sample"], ch["interval_seconds"]
    if n < 0 or b < 0 or dt <= 0:
        raise ValueError("Invalid channel count, bits or sampling interval")
    return n * b / dt

def engineering(name, p):
    """Independent engineering equations; values remain preliminary."""
    if name == "eps_hk":
        bol = p["cell_power_w"] * p["assembly_factor"] * math.cos(math.radians(p["incidence_deg"]))
        eol = bol * (1 - p["annual_degradation"]) ** p["lifetime_years"]
        required = ((p["eclipse_load_w"] * p["eclipse_hours"] / p["eclipse_efficiency"])
                    + (p["sunlit_load_w"] * p["sunlit_hours"] / p["day_efficiency"])) / p["sunlit_hours"]
        capacity = p["eclipse_load_w"] * p["eclipse_hours"] / (p["max_dod"] * p["battery_branches"] * p["discharge_efficiency"])
        return {"p_bol_w": bol, "p_eol_w": eol, "required_solar_power_w": required,
                "solar_area_m2": required / p["eol_specific_power_w_m2"],
                "battery_capacity_required_wh": capacity,
                "source_equations": "lecture EPS 6.1-6.2"}
    if name == "aocs_nominal_hk":
        slew = 4 * math.radians(p["slew_angle_deg"]) * p["inertia_kg_m2"] / p["slew_seconds"]**2
        grav = 3 * p["mu_m3_s2"] * abs(p["inertia_z"] - p["inertia_y"]) * abs(math.sin(2 * math.radians(p["gravity_angle_deg"]))) / (2 * p["orbit_radius_m"]**3)
        return {"slew_torque_nm": slew, "gravity_gradient_torque_nm": grav,
                "reaction_wheel_torque_requirement_nm": max(slew, grav) * p["torque_margin_factor"],
                "source_equations": "lecture AOCS 4.1-4.2"}
    if name == "propulsion_hk":
        prop = p["initial_mass_kg"] * (1 - math.exp(-p["delta_v_m_s"] / (p["isp_s"] * G0)))
        return {"propellant_required_kg": prop, "final_mass_kg": p["initial_mass_kg"] - prop,
                "source_equations": "lecture Propulsion 5.1 Tsiolkovsky"}
    if name == "thermal_hk":
        absorbed = p["absorptivity"] * p["solar_flux_w_m2"] * p["projected_area_m2"] + p["internal_heat_w"]
        temp = (absorbed / (p["emissivity"] * SIGMA * p["radiator_area_m2"]))**0.25
        return {"equilibrium_temperature_k": temp, "absorbed_heat_w": absorbed,
                "source_equations": "lecture TCS 7.1; excludes albedo and IR for lunar scenario"}
    if name == "structures_mechanisms":
        design = p["limit_load_n"] * p["factor_of_safety"]
        return {"design_load_n": design, "margin_of_safety": p["allowable_load_n"] / design - 1,
                "source_equations": "lecture Structures 9"}
    if name == "payload_housekeeping":
        return {"pnt_broadcast_excluded": True,
                "note": "Lunar PNT RF broadcast is not Earth-directed housekeeping; optical/SAR lecture formulas do not apply to SELENA PNT."}
    if name == "obdh_hk_logs":
        return {"software_memory_bytes": p["sloc"] * p["bytes_per_sloc"],
                "cpu_kips_reference": sum(p["cpu_task_kips"]),
                "note": "KIPS is processing load, not telemetry bits/s.",
                "source_equations": "lecture OBDH 1.2-1.3"}
    raise ValueError("Unknown subsystem: " + name)

def validation_status(source_type, origin, reference, delta):
    """Say what a match with the PDF aggregate does and does not prove."""
    if origin == "MISSING_INPUT":
        return "MISSING_INPUT"
    if origin == "PDF_AGGREGATE_FALLBACK":
        return "DOC_AGGREGATE_ONLY_NO_CHANNEL_INVENTORY"
    if reference is None:
        return "ASSUMED_INVENTORY_NO_PDF_REFERENCE"
    if abs(delta) < 1e-9:
        if str(source_type).startswith("REVERSE_ENGINEERED"):
            return "MATCHES_PDF_BY_CONSTRUCTION_NOT_INDEPENDENT_VERIFICATION"
        return "MATCHES_PDF_REFERENCE"
    return "DIFFERS_FROM_PDF_REFERENCE_INVESTIGATE"


def telemetry_rows(telemetry_cfg):
    """Single implementation of the per-subsystem data-generation rate.

    Channels win: rate = sum(count x bits / interval). The documented (PDF) aggregate is only a
    reference (shown with its difference) or, when no channel inventory exists, the fallback.
    A subsystem with neither is reported as MISSING_INPUT (rate None), never as zero.
    """
    rows = []
    for subsystem in telemetry_cfg["subsystems"]:
        channels = subsystem.get("components", [])
        reference = subsystem.get("pdf_rate_bps")
        reference = None if reference is None else float(reference)
        if channels:
            rate = sum(channel_rate(c) for c in channels)
            origin = "CALCULATED_FROM_CHANNELS" if subsystem["source_type"] == "PDF" else "CALCULATED_FROM_CHANNELS_PLACEHOLDER"
        elif reference is not None:
            rate, origin = reference, "PDF_AGGREGATE_FALLBACK"
        else:
            rate, origin = None, "MISSING_INPUT"
        delta = None if rate is None or reference is None else rate - reference
        public_type = ("MISSING_INPUT" if rate is None else
                       "PDF" if origin == "PDF_AGGREGATE_FALLBACK" or subsystem["source_type"] == "PDF" else
                       "PRELIMINARY_ESTIMATE")
        rows.append({"subsystem": subsystem["name"], "rate_bps": rate,
                     "mbit_per_day": None if rate is None else rate*DAY/1e6,
                     "mb_per_day": None if rate is None else rate*DAY/8e6,
                     "telemetry_origin": origin, "source_type": public_type,
                     "input_source_type": subsystem["source_type"], "source": subsystem.get("source"),
                     "requires_confirmation": public_type != "PDF",
                     "pdf_reference_bps": reference, "difference_from_pdf_bps": delta,
                     "validation_status": validation_status(subsystem["source_type"], origin, reference, delta),
                     "channel_count": sum(c["count"] for c in channels),
                     "channels": [{**c, "rate_bps": channel_rate(c)} for c in channels]})
    return rows


def totals(rows, n_satellites):
    known = [r["rate_bps"] for r in rows if r["rate_bps"] is not None]
    total = sum(known)
    return {"total_rate_bps_per_spacecraft": total,
            "total_mbit_per_day_per_spacecraft": total*DAY/1e6,
            "total_mb_per_day_per_spacecraft": total*DAY/8e6,
            "total_mbit_per_day_constellation": total*DAY/1e6*n_satellites,
            "total_mb_per_day_constellation": total*DAY/8e6*n_satellites,
            "n_satellites": n_satellites,
            "missing_subsystems": [r["subsystem"] for r in rows if r["rate_bps"] is None],
            "telemetry_complete": all(r["rate_bps"] is not None for r in rows)}


def calculate(telemetry_cfg, engineering_cfg):
    models = engineering_cfg["subsystems"]
    rows = telemetry_rows(telemetry_cfg)
    for row in rows:
        name = row["subsystem"]
        if name not in models:
            raise ValueError("Missing engineering model: " + name)
        row["engineering"] = engineering(name, models[name])
        row["engineering_input_origin"] = models[name]["origin"]
    return {"status": "PRELIMINARY_PLACEHOLDERS_NOT_VALIDATED",
            "scope": "one spacecraft; housekeeping for Earth downlink, no lunar PNT broadcast",
            "subsystems": rows, **totals(rows, int(load_parameters()["n_satellites"])),
            "validation_warning": "A rate that matches a PDF aggregate by reverse engineering is NOT independent verification. Engineering equations (EPS, AOCS, propulsion, thermal, structures, OBDH) size hardware; they do not determine the telemetry rates, which come only from the channel inventories.",
            "warning": "Engineering outputs and sensor inventories are preliminary; equations do not determine sampling rates."}

def compute(telemetry_path="data/telemetry_generation_inputs.json",
            engineering_path="data/subsystem_engineering_inputs.json", output_dir="outputs"):
    t = json.loads(Path(telemetry_path).read_text(encoding="utf-8"))
    e = json.loads(Path(engineering_path).read_text(encoding="utf-8"))
    result = calculate(t, e)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out/"subsystem_engineering.json").write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return result

if __name__ == "__main__":
    print(json.dumps(compute(), indent=2))
