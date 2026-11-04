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

PARAMS = ("count", "bits_per_sample", "interval_seconds")
PROVENANCE = ("DOC", "OWNER", "ASSUMPTION", "UNKNOWN")
CONFIRMED = ("DOC", "OWNER")


def channel_rate(ch):
    """Rate of a COMPLETE channel: count x bits / interval. Raises if a parameter is unknown."""
    n, b, dt = ch["count"], ch["bits_per_sample"], ch["interval_seconds"]
    if n is None or b is None or dt is None:
        raise ValueError("Channel is incomplete (unknown count, bits or interval): no rate can be computed")
    if n < 0 or b < 0 or dt <= 0:
        raise ValueError("Invalid channel count, bits or sampling interval")
    return n * b / dt


def channel_provenance(ch):
    """Origin of each channel parameter: DOC (PDF), OWNER (confirmed), ASSUMPTION or UNKNOWN."""
    given = ch.get("provenance", "ASSUMPTION")
    if isinstance(given, str):
        given = {k: given for k in PARAMS}
    out = {}
    for k in PARAMS:
        value = ch.get(k)
        origin = given.get(k, "ASSUMPTION")
        if origin not in PROVENANCE:
            raise ValueError("Unknown provenance: " + str(origin))
        if value is None:
            out[k] = "UNKNOWN"
        elif origin == "UNKNOWN":
            out[k] = "ASSUMPTION"  # a value supplied for a previously unknown parameter (what-if) is an assumption
        else:
            out[k] = origin
    return out


def validation_status(reference, itemised, remainder, complete, has_complete_channels, incomplete):
    """Say what the numbers do and do not prove."""
    if reference is None:
        if not has_complete_channels:
            return "MISSING_INPUT"
        return "INVENTORY_INCOMPLETE_RATE_IS_LOWER_BOUND" if incomplete else "ASSUMED_INVENTORY_NO_PDF_REFERENCE"
    if complete:
        return ("ITEMISATION_COMPLETE_MATCHES_PDF" if abs(itemised - reference) < 1e-9
                else "ITEMISATION_COMPLETE_DIFFERS_FROM_PDF_SEE_DIFFERENCE")
    if itemised > reference + 1e-9:
        return "ITEMISED_EXCEEDS_PDF_AGGREGATE_INVESTIGATE"
    if remainder < 1e-9:
        return "ITEMISED_EQUALS_PDF_COMPLETENESS_UNCONFIRMED"
    return "PDF_AGGREGATE_PROVISIONAL_ITEMISATION_PENDING"


def telemetry_rows(telemetry_cfg):
    """Single implementation of the per-subsystem data-generation rate.

    * A channel counts only when count, bits and interval are all known; unknown parameters are
      never filled in. Incomplete channels are listed with what is missing.
    * itemised = sum of the counted channels.
    * With a documented (PDF) aggregate and an incomplete itemisation, the rate used for TT&C
      sizing is the aggregate (provisional) and the part not yet itemised is shown separately:
      unitemised remainder = aggregate - itemised. If the itemised channels exceed the aggregate,
      the itemised sum is used and the case is flagged. When the owner declares the itemisation
      complete, the rate is the itemised sum and the difference from the PDF is shown, not forced.
    * No inventory and no reference: MISSING_INPUT (rate None), never zero.
    """
    rows = []
    for subsystem in telemetry_cfg["subsystems"]:
        channels = []
        for c in subsystem.get("components", []):
            prov = channel_provenance(c)
            missing = [k for k in PARAMS if c.get(k) is None]
            counted = not missing
            channels.append({"name": c["name"], **{k: c.get(k) for k in PARAMS},
                             "rate_bps": channel_rate(c) if counted else None, "counted": counted,
                             "provenance": prov, "missing_parameters": missing,
                             "source": c.get("source", subsystem.get("source")), "owner_todo": c.get("owner_todo")})
        counted_channels = [c for c in channels if c["counted"]]
        incomplete = [c["name"] for c in channels if not c["counted"]]
        itemised = sum(c["rate_bps"] for c in counted_channels)
        reference = subsystem.get("pdf_rate_bps")
        reference = None if reference is None else float(reference)
        complete = bool(subsystem.get("itemisation_complete", False))
        if reference is None:
            rate = itemised if counted_channels else None
            remainder = None
            basis = "MISSING_INPUT" if rate is None else (
                "CHANNELS_ASSUMED" if any("ASSUMPTION" in c["provenance"].values() for c in counted_channels) else "CHANNELS_DOCUMENTED")
        elif complete:
            rate, remainder, basis = itemised, 0.0, "CHANNELS_ITEMISATION_COMPLETE"
        elif itemised > reference + 1e-9:
            rate, remainder, basis = itemised, 0.0, "ITEMISED_EXCEEDS_PDF_AGGREGATE"
        else:
            rate, remainder, basis = reference, reference - itemised, "PDF_AGGREGATE_PROVISIONAL"
        estimated = any("ASSUMPTION" in c["provenance"].values() for c in counted_channels)
        public_type = ("MISSING_INPUT" if rate is None else
                       "PDF" if basis == "PDF_AGGREGATE_PROVISIONAL" or (not estimated and basis != "CHANNELS_ASSUMED") else
                       "PRELIMINARY_ESTIMATE")
        pending = rate is None or not (complete and not estimated and not incomplete)
        rows.append({"subsystem": subsystem["name"], "rate_bps": rate,
                     "mbit_per_day": None if rate is None else rate*DAY/1e6,
                     "mb_per_day": None if rate is None else rate*DAY/8e6,
                     "rate_basis": basis, "source_type": public_type,
                     "input_source_type": subsystem["source_type"], "source": subsystem.get("source"),
                     "requires_confirmation": pending,
                     "itemised_bps": itemised if (counted_channels or reference is not None) else None,
                     "unitemised_remainder_bps": remainder, "itemisation_complete": complete,
                     "pdf_reference_bps": reference,
                     "difference_from_pdf_bps": None if rate is None or reference is None else rate - reference,
                     "itemised_minus_pdf_bps": None if reference is None else itemised - reference,
                     "validation_status": validation_status(reference, itemised, remainder, complete,
                                                            bool(counted_channels), incomplete),
                     "incomplete_channels": [{"name": c["name"], "missing_parameters": c["missing_parameters"]}
                                             for c in channels if not c["counted"]],
                     "owner_todo": subsystem.get("owner_todo"),
                     "channel_count": sum(c["count"] for c in counted_channels),
                     "channels": channels})
    return rows


def totals(rows, n_satellites):
    known = [r["rate_bps"] for r in rows if r["rate_bps"] is not None]
    total = sum(known)
    remainder = sum(r["unitemised_remainder_bps"] or 0.0 for r in rows)
    itemised = sum(r["itemised_bps"] or 0.0 for r in rows)
    return {"total_rate_bps_per_spacecraft": total,
            "total_itemised_bps_per_spacecraft": itemised,
            "total_unitemised_remainder_bps_per_spacecraft": remainder,
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
            "validation_warning": "Documented (PDF) aggregates are provisional sizing values: the part not itemised by documented channels is shown separately as the unitemised remainder. A rate that matches a PDF aggregate only by construction is NOT independent verification. Engineering equations (EPS, AOCS, propulsion, thermal, structures, OBDH) size hardware; they do not determine the telemetry rates, which come only from the channel inventories.",
            "warning": "Engineering outputs and sensor inventories are preliminary; equations do not determine sampling rates."}


def engineering(name, p):
    """Independent engineering equations; values remain preliminary."""
    if name == "eps_hk":
        # Single methodology (lecture EPS 6.1-6.2): P_BOL = P0*Id*cos(theta); P_EOL = P_BOL*(1-d)^L;
        # P_sa = (Pe*Te/Xe + Pd*Td/Xd)/Td; A = P_sa/P_EOL; C = Pe*Te/(DoD*N*eta).
        # No parameter is fitted to a PDF value; PDF values appear only as a reference block.
        bol = p["cell_specific_power_w_m2"] * p["assembly_factor"] * math.cos(math.radians(p["incidence_deg"]))
        eol = bol * (1 - p["annual_degradation"]) ** p["lifetime_years"]
        required = ((p["eclipse_load_w"] * p["eclipse_hours"] / p["eclipse_efficiency"])
                    + (p["sunlit_load_w"] * p["sunlit_hours"] / p["day_efficiency"])) / p["sunlit_hours"]
        capacity = p["eclipse_load_w"] * p["eclipse_hours"] / (p["max_dod"] * p["battery_branches"] * p["discharge_efficiency"])
        area = required / eol
        out = {"p_bol_w_m2": bol, "p_eol_w_m2": eol, "required_solar_power_w": required,
               "solar_area_m2": area, "battery_capacity_required_wh": capacity,
               "area_method": "A = P_sa / P_EOL (lecture); no back-solved specific power",
               "source_equations": "lecture EPS 6.1-6.2"}
        ref = p.get("pdf_reference")
        if ref:
            out["pdf_reference"] = {
                "array_eol_w": ref["array_eol_w"], "battery_wh": ref["battery_wh"],
                "required_solar_power_minus_pdf_array_w": required - ref["array_eol_w"],
                "battery_capacity_minus_pdf_wh": capacity - ref["battery_wh"],
                "area_for_pdf_array_at_modelled_eol_power_m2": ref["array_eol_w"] / eol,
                "pdf_solar_area_m2": None,
                "note": "The PDF gives no solar array area; differences are shown, not removed. eclipse_hours and cell_specific_power_w_m2 are owner TODOs."}
        return out
    if name == "aocs_nominal_hk":
        slew = 4 * math.radians(p["slew_angle_deg"]) * p["inertia_kg_m2"] / p["slew_seconds"]**2
        k = 3 * p["mu_m3_s2"] * abs(p["inertia_z"] - p["inertia_y"]) * abs(math.sin(2 * math.radians(p["gravity_angle_deg"]))) / 2
        rp, ra = p.get("periapsis_radius_m"), p.get("apoapsis_radius_m")
        r_used = p["orbit_radius_m"]
        out = {"slew_torque_nm": slew}
        if rp is not None:
            r_used, basis = rp, "PERIAPSIS_RADIUS"
            out["gravity_gradient_torque_periapsis_nm"] = k / rp**3
            if ra is not None:
                # r(nu)=a(1-e^2)/(1+e cos nu); orbit time average <r^-3> = a^-3 (1-e^2)^(-3/2)
                a_sm = (rp + ra) / 2
                ecc = (ra - rp) / (ra + rp)
                out.update({"gravity_gradient_torque_apoapsis_nm": k / ra**3,
                            "gravity_gradient_torque_orbit_average_nm": k * a_sm**-3 * (1 - ecc**2)**-1.5,
                            "semi_major_axis_m": a_sm, "eccentricity": ecc})
        else:
            basis = "CIRCULAR_RADIUS_LOWER_BOUND_PERIAPSIS_INPUT_NEEDED"
        grav = k / r_used**3
        margin = p["torque_margin_factor"]
        out.update({"gravity_gradient_torque_nm": grav, "radius_used_m": r_used, "radius_basis": basis,
                    "reaction_wheel_torque_requirement_nm": (slew + grav) * margin,
                    "reaction_wheel_torque_max_only_nm": max(slew, grav) * margin,
                    "torque_combination": "worst case: slew + gravity gradient at the same time, times margin; other disturbances (solar pressure, residual dipole, thrust misalignment) not available: owner TODO",
                    "source_equations": "lecture AOCS 4.1-4.2; r(nu) = a(1-e^2)/(1+e cos nu)"})
        return out
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
