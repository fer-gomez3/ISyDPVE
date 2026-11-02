from pathlib import Path

import pytest

from ttc.contacts import export_csv, parse_contacts


EXAMPLE = (
    "Goldstone --> SELENA_21 Jan 01 2020 00:02:00.000000000 "
    "Jan 01 2020 05:44:01.347656250 342.022460938"
)


def test_parse_and_preserve_original_duration():
    contacts = parse_contacts(EXAMPLE)
    assert len(contacts) == 1
    assert contacts[0].station == "Goldstone"
    assert contacts[0].satellite == "SELENA_21"
    assert contacts[0].duration_source_min == 342.022460938
    assert abs(contacts[0].duration_difference_sec) < 0.001


def test_reject_unrecognized_input():
    with pytest.raises(ValueError, match="No DSN contacts"):
        parse_contacts("not a contact export")


def test_csv_export(tmp_path: Path):
    target = tmp_path / "windows.csv"
    export_csv(parse_contacts(EXAMPLE), target)
    assert "duration_source_min" in target.read_text(encoding="utf-8")
