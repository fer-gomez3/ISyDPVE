import json
import sys
from pathlib import Path
import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    import os
    from main import main
    out = tmp_path_factory.mktemp("out")
    link = tmp_path_factory.mktemp("lk") / "link.json"
    link.write_text(json.dumps({"distance_km": 400000, "rx_gt_db_per_k": 30, "required_ebn0_db": 10,
                                "losses_db": 3, "margin_db": 3, "pa_efficiency": 0.4, "electronics_w": 5}))
    old = os.getcwd(); os.chdir(ROOT)
    argv = sys.argv
    sys.argv = ["main.py", "--output-dir", str(out), "--link-input", str(link)]
    try:
        summary = main()
    finally:
        sys.argv = argv; os.chdir(old)
    return out, summary


def test_hga_gain_is_wired_into_link_budget(built):
    out, summary = built
    link = json.loads((out / "link_budget.json").read_text())
    hga = json.loads((out / "hga_sizing.json").read_text())
    assert link["status"] == "PRELIMINARY"
    assert link["minimum_tx_rf_w_with_design_margin"] > 0
    assert hga["calculated_idealized_gain_dbi"] == pytest.approx(28.269, abs=1e-3)


def test_workbook_has_live_formulas_and_numeric_cells(built):
    out, _ = built
    wb = openpyxl.load_workbook(out / "SELENA_TTC_Model.xlsx")
    for name in ("Inputs", "Telemetry", "Capacity", "HGA", "Link", "Power"):
        assert name in wb.sheetnames
    formulas = sum(1 for ws in wb for row in ws.iter_rows() for c in row
                   if isinstance(c.value, str) and c.value.startswith("="))
    assert formulas > 40
    dc = wb["Downlink Contacts"]
    header = [c.value for c in dc[1]]
    assert isinstance(dc.cell(2, header.index("capacity_mbit") + 1).value, (int, float))
    assert "Link" in wb.sheetnames and "Satellites" in wb.sheetnames and "Stations" in wb.sheetnames


def test_missing_link_inputs_are_flagged_not_invented(tmp_path):
    from ttc.export_workbook import export
    import os
    old = os.getcwd(); os.chdir(ROOT)
    try:
        wb = openpyxl.load_workbook(export(output=str(tmp_path / "w.xlsx"), out_dir=str(tmp_path)))
    finally:
        os.chdir(old)
    inp = {r[0]: r for r in wb["Inputs"].iter_rows(min_row=2, values_only=True)}
    assert inp["gt_dbk"][2] is None and inp["gt_dbk"][4] == "INPUT NEEDED"
