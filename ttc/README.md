# SELENA — TT&C / DSN visibility

Two separate tools:

1. `python -m ttc.contacts data/raw/Contactos_con_DSN.txt`: import **previously calculated** contact windows.
2. `python -m ttc.visibility data/raw/satellite_ephemeris.csv`: compute **sampled geometric visibility** from lunar spacecraft positions and time-dependent Earth station positions.

See [`ephemeris_format.md`](ephemeris_format.md) for the strict input coordinate-frame contract. The visibility module does **not yet** extract precise start/end contact windows; this is the next development step.

Install dependencies with `pip install -r requirements.txt` and run `python -m pytest`.

The original 112-contact propagator export and actual spacecraft ephemerides have not yet been uploaded. Station coordinates are approximate and DSN antenna allocation is not modeled.
