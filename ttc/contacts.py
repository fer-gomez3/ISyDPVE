"""Parse SELENA DSN contact windows without modifying the source durations."""
from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
import re

_TIMESTAMP = r"[A-Za-z]{3}\s+\d{1,2}\s+\d{4}\s+\d{2}:\d{2}:\d{2}\.\d+"
_PATTERN = re.compile(
    rf"(?P<station>Goldstone|Madrid|Canberra)\s*-->\s*"
    rf"(?P<satellite>SELENA_\d+)\s+"
    rf"(?P<start>{_TIMESTAMP})\s+"
    rf"(?P<end>{_TIMESTAMP})\s+"
    rf"(?P<duration>\d+(?:\.\d+)?)",
    flags=re.IGNORECASE,
)


def parse_timestamp(value: str) -> datetime:
    """Parse nanosecond-like input as a microsecond-resolution UTC-naive datetime."""
    head, fraction = value.rsplit(".", 1)
    return datetime.strptime(head, "%b %d %Y %H:%M:%S").replace(
        microsecond=int((fraction + "000000")[:6])
    )


@dataclass(frozen=True)
class Contact:
    station: str
    satellite: str
    start_utc: str
    end_utc: str
    duration_source_min: float
    duration_computed_min: float
    duration_difference_sec: float


def parse_contacts(text: str) -> list[Contact]:
    contacts = []
    for match in _PATTERN.finditer(text):
        start = parse_timestamp(match["start"])
        end = parse_timestamp(match["end"])
        if end < start:
            raise ValueError(f"Contact ends before it begins: {match.group(0)}")
        source = float(match["duration"])
        computed = (end - start).total_seconds() / 60
        contacts.append(Contact(
            station=match["station"].title(),
            satellite=match["satellite"].upper(),
            start_utc=start.isoformat(sep=" "),
            end_utc=end.isoformat(sep=" "),
            duration_source_min=source,
            duration_computed_min=computed,
            duration_difference_sec=(computed - source) * 60,
        ))
    if not contacts:
        raise ValueError("No DSN contacts found; check the propagator export format.")
    return contacts


def export_csv(contacts: list[Contact], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Contact.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(contact) for contact in contacts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize SELENA DSN contact windows")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("outputs/contact_windows.csv"))
    args = parser.parse_args()
    contacts = parse_contacts(args.source.read_text(encoding="utf-8"))
    export_csv(contacts, args.output)
    print(f"Exported {len(contacts)} contacts to {args.output}")
    print(f"Satellites: {len({c.satellite for c in contacts})}; stations: {len({c.station for c in contacts})}")
    print(f"Largest duration discrepancy: {max(abs(c.duration_difference_sec) for c in contacts):.4f} s")


if __name__ == "__main__":
    main()
