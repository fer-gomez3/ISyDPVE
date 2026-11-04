import json
from pathlib import Path
import openpyxl
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_hga_gain_is_wired_into_link_budget(run_linked):
    out, _ = run_linked
    link = json.loads((out / "link_budget.json").read_text())
    hga = json.loads((out / "hga_sizing.json").read_text())
    assert link["status"] == "PRELIMINARY"
    assert link["minimum_tx_rf_w_with_design_margin"] > 0
    assert hga["calculated_idealized_gain_dbi"] == pytest.approx(28.269, abs=1e-3)


def test_workbook_has_live_formulas_and_numeric_cells(run_linked):
    out, _ = run_linked
    wb = openpyxl.load_workbook(out / "SELENA_TTC_Model.xlsx")
    for name in ("Inputs", "Telemetry", "Capacity", "HGA", "Link", "Power", "Satellites", "Stations",
                 "DSN Allocation", "Checks", "RF Trade Cases", "Limitations"):
        assert name in wb.sheetnames
    formulas = sum(1 for ws in wb for row in ws.iter_rows() for c in row
                   if isinstance(c.value, str) and c.value.startswith("="))
    assert formulas > 60
    dc = wb["Downlink Contacts"]
    header = [c.value for c in dc[1]]
    assert isinstance(dc.cell(2, header.index("capacity_mbit") + 1).value, (int, float))


def test_missing_link_inputs_are_flagged_not_invented(run_default):
    out, _ = run_default
    wb = openpyxl.load_workbook(out / "SELENA_TTC_Model.xlsx")
    inp = {r[0]: r for r in wb["Inputs"].iter_rows(min_row=2, values_only=True)}
    for name in ("dist_km", "gt_dbk", "ebn0_db", "loss_db", "margin_db"):
        assert inp[name][2] is None and inp[name][4] == "INPUT NEEDED"
    link = json.loads((out / "link_budget.json").read_text())
    assert link["status"] == "MISSING_INPUTS" and "tx_gain_dbi" not in link["missing_inputs"]
