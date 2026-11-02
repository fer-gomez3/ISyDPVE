# SELENA — TT&C and DSN contact analysis

Initial scope: parse propagator contact windows; preserve station, spacecraft, start/end UTC, and the propagator's original duration; check consistency; export normalized CSV and station/satellite summaries.

## Quick start

```bash
python -m ttc.contacts data/raw/Contactos_con_DSN.txt --output outputs/contact_windows.csv
python -m pytest
```

Place the **original** `Contactos_con_DSN.txt` in `data/raw/` before running the importer. It has not yet been uploaded to this repository. Input times are interpreted as UTC. A small synthetic fixture is included for testing only.

## Next increments

1. Import and validate all 112 real windows (once original file is added).
2. Model scheduling conflicts, DSN allocation and minimum usable contact duration.
3. Add telemetry volume, link budget, OBDH storage, EPS, thermal and ADCS interfaces.
4. Generate a multi-sheet Excel engineering report from the validated model.
