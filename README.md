# SELENA TT&C / OBDH preliminary model

## Install and run (Python 3.11+)

Download the **feature/ttc-initial-structure** branch ZIP from GitHub, extract it, and open a terminal in the extracted repository folder (the folder containing `main.py`).

Windows PowerShell:
```powershell
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
```

macOS/Linux:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python main.py
```

Results are written to `outputs/`, including `SELENA_TTC_Model.xlsx` and `overview.json`.

## Important limitations

This is a **preliminary scenario model**, not validated 2030 geometry or confirmed DSN bookings. Historical contact windows are shifted in calendar time; they are not physically propagated to 2030. The X-band antenna gain, power and link assumptions are provisional, not selected flight hardware. The HGA pointing gimbal (1.50 kg basic, 2.0 W nominal) is included in Structures, not TT&C mass; the reflector/feed still requires sizing.

Run from the repository root because scenario paths are relative. Installation requires internet to download dependencies. If `artifact-tool` fails to install on your Python version, try Python 3.11 or 3.12.
