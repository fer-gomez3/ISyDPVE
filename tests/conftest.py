"""Shared fixtures: run the full pipeline once per session in a temporary output directory."""
import json
import os
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
LINK_TEST = {"distance_km": 400000, "rx_gt_db_per_k": 30, "required_ebn0_db": 10, "losses_db": 3,
             "margin_db": 3, "pa_efficiency": 0.4, "electronics_w": 5, "standby_w": 2}


def _run(out, link_path=None):
    from main import main
    old, argv = os.getcwd(), sys.argv
    os.chdir(ROOT)
    sys.argv = ["main.py", "--output-dir", str(out)] + (["--link-input", str(link_path)] if link_path else [])
    try:
        return main()
    finally:
        sys.argv = argv
        os.chdir(old)


@pytest.fixture(scope="session")
def run_default(tmp_path_factory):
    out = tmp_path_factory.mktemp("default")
    return out, _run(out)


@pytest.fixture(scope="session")
def run_linked(tmp_path_factory):
    out = tmp_path_factory.mktemp("linked")
    link = tmp_path_factory.mktemp("lk") / "link.json"
    link.write_text(json.dumps(LINK_TEST))
    return out, _run(out, link)
