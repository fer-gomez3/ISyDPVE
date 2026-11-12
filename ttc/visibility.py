"""Compute geometric Earth-to-lunar-spacecraft visibility from sampled ephemerides.

Input positions are Moon-centered, but axes MUST be aligned with geocentric GCRS.
Output boundaries are sampled (not interpolated), so timing precision is limited
by the input sampling cadence. DSN scheduling is NOT modeled.
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from astropy import units as u
from astropy.coordinates import EarthLocation, get_body
from astropy.time import Time

# Approximate publicly documented DSN complex reference locations.
# Replace with authoritative antenna geodetic coordinates for final analysis.
STATIONS = {
    "Goldstone": (-116.8889, 35.4267, 1000.0),
    "Madrid": (-4.2486, 40.4314, 800.0),
    "Canberra": (148.9819, -35.3985, 700.0),
}
MOON_RADIUS_KM = 1737.4


def utc_time(value: str) -> Time:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Input UTC timestamp must include 'Z' or an offset")
    return Time(dt.astimezone(timezone.utc))


def station_gcrs(name: str, time: Time) -> tuple[np.ndarray, np.ndarray]:
    """Station geocentric GCRS position (km) and outward zenith unit vector."""
    lon, lat, height = STATIONS[name]
    site = EarthLocation.from_geodetic(lon * u.deg, lat * u.deg, height * u.m)
    pos, _ = site.get_gcrs_posvel(time)
    r = pos.xyz.to_value(u.km)
    # Geodetic zenith is normal to the reference ellipsoid, not exactly radial.
    surface = EarthLocation.from_geodetic(lon * u.deg, lat * u.deg, (height + 1000) * u.m)
    upper, _ = surface.get_gcrs_posvel(time)
    zenith = upper.xyz.to_value(u.km) - r
    return r, zenith / np.linalg.norm(zenith)


def moon_gcrs(time: Time) -> np.ndarray:
    return get_body("moon", time).cartesian.xyz.to_value(u.km)


def segment_occulted(start: np.ndarray, end: np.ndarray, center: np.ndarray,
                     radius_km: float = MOON_RADIUS_KM) -> bool:
    """True when the finite station-to-satellite segment intersects lunar sphere."""
    direction = end - start
    length2 = float(np.dot(direction, direction))
    if length2 == 0:
        return False
    fraction = np.clip(np.dot(center - start, direction) / length2, 0.0, 1.0)
    closest = start + fraction * direction
    return bool(np.linalg.norm(closest - center) <= radius_km)


def visibility(time: Time, station: str, satellite_moon_gcrs_km: np.ndarray,
               min_elevation_deg: float = 10.0) -> tuple[bool, float, bool]:
    station_pos, zenith = station_gcrs(station, time)
    moon = moon_gcrs(time)
    satellite = moon + satellite_moon_gcrs_km
    ray = satellite - station_pos
    ray /= np.linalg.norm(ray)
    elevation = float(np.degrees(np.arcsin(np.clip(np.dot(ray, zenith), -1, 1))))
    occulted = segment_occulted(station_pos, satellite, moon)
    return elevation >= min_elevation_deg and not occulted, elevation, occulted


def analyze_csv(source: Path, output: Path, min_elevation_deg: float = 10.0) -> int:
    """Read sampled ephemerides and output one visibility result per station/sample."""
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with source.open(newline="", encoding="utf-8") as inp, output.open(
        "w", newline="", encoding="utf-8"
    ) as out:
        reader = csv.DictReader(inp)
        required = {"time_utc", "satellite", "x_moon_gcrs_km", "y_moon_gcrs_km", "z_moon_gcrs_km"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError(f"Required columns: {sorted(required)}")
        writer = csv.DictWriter(out, fieldnames=[
            "time_utc", "satellite", "station", "visible", "elevation_deg", "moon_occulted"
        ])
        writer.writeheader()
        for record in reader:
            t = utc_time(record["time_utc"])
            vector = np.array([float(record[key]) for key in (
                "x_moon_gcrs_km", "y_moon_gcrs_km", "z_moon_gcrs_km"
            )])
            for station in STATIONS:
                is_visible, elevation, occulted = visibility(t, station, vector, min_elevation_deg)
                writer.writerow({
                    "time_utc": t.utc.isot + "Z", "satellite": record["satellite"],
                    "station": station, "visible": int(is_visible),
                    "elevation_deg": round(elevation, 5), "moon_occulted": int(occulted),
                })
                count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute sampled SELENA DSN visibility")
    parser.add_argument("ephemeris", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/visibility_samples.csv"))
    parser.add_argument("--min-elevation", type=float, default=10.0)
    args = parser.parse_args()
    count = analyze_csv(args.ephemeris, args.output, args.min_elevation)
    print(f"Wrote {count} station-satellite samples to {args.output}")


if __name__ == "__main__":
    main()
