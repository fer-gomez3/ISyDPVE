# ISyDPVE — Architecture

The repository hosts the SELENA lunar PNT mission systems-engineering models.

- `ttc/`: Earth-facing telemetry, tracking and command analysis.
- `data/raw/`: original propagation/contact exports, preserved unchanged.
- `data/processed/`: normalized, traceable datasets.
- `outputs/`: generated reports, not authoritative source inputs.
- `tests/`: repeatable validation.

## Ground rules

Geometric visibility is **not** a confirmed DSN antenna allocation. Historical contact epochs may be used to test durations and algorithms, but must not be presented as future operational schedules. Engineering assumptions must be explicitly labeled and tracked.
