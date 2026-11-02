# Input orbital ephemeris contract

Provide a CSV with columns:

```csv
time_utc,satellite,x_moon_gcrs_km,y_moon_gcrs_km,z_moon_gcrs_km
```

- `time_utc`: ISO 8601 UTC including `Z` or explicit timezone offset.
- `satellite`: e.g. `SELENA_11`.
- x/y/z: satellite position relative to the **Moon's center**, in **km**, with axes parallel to Earth's **GCRS** frame at that timestamp.
- These are **not** Moon-fixed coordinates, nor Keplerian elements. Convert those first using a documented reference frame and epoch.
- At least one sample per desired output time. Use fine time spacing near visibility transitions.
- The calculation uses approximate complex reference locations and a spherical lunar occultation model.
- Visibility is geometric only; not a DSN reservation, nor a radio link-budget check.
- Moon positions use Astropy solar-system ephemerides; higher-fidelity SPICE/JPL and Earth orientation data should be used for mission-grade analysis.

Run:

```bash
python -m ttc.visibility data/raw/satellite_ephemeris.csv --output outputs/visibility_samples.csv --min-elevation 10
```

The initial implementation writes **sample-by-sample visibility**, not precise start/end windows. Window detection and boundary interpolation are the next development step.
