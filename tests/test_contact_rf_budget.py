"""Antenna / RF budget from assigned contacts: closed forms, modes, missing data, coherence.

Synthetic contacts and illustrative parameters test the calculation chain, not
engineering values.
"""
import csv
import json
import math
import tempfile
import unittest
from pathlib import Path

from ttc import contact_rf_budget as rf
from ttc import dsn_pipeline
from ttc.integrated_requirements import build
from ttc.link_budget import evaluate_link

FIELDS = ["satellite", "station", "start_utc", "end_utc", "reserved_minutes", "tx_start_utc", "tx_end_utc",
          "useful_tx_minutes", "backlog_at_tx_start_mbit", "downloaded_mbit", "backlog_after_tx_mbit",
          "backlog_drained_at_tx_end", "status"]
LINK = dict(frequency_hz=8.4e9, distance_km=405000, rx_gt_db_per_k=45, required_ebn0_db=6, losses_db=4,
            margin_db=3, pointing_error_deg=0.15, aperture_efficiency=0.55, pa_efficiency=0.35, electronics_w=8,
            diameter_m=0.38)
GEN, OVH = 2301.74, 0.2


def contact(sat, start, tx_start, tx_end, end, backlog, after=0.0, status=rf.ASSIGNED):
    from datetime import datetime
    mins = lambda a, b: (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 60
    return {"satellite": sat, "station": "Goldstone", "start_utc": start, "end_utc": end,
            "reserved_minutes": mins(start, end), "tx_start_utc": tx_start, "tx_end_utc": tx_end,
            "useful_tx_minutes": mins(tx_start, tx_end), "backlog_at_tx_start_mbit": backlog,
            "downloaded_mbit": backlog, "backlog_after_tx_mbit": after,
            "backlog_drained_at_tx_end": after < 1e-3, "status": status}


def write_contacts(directory, rows):
    with (Path(directory) / "assigned_contacts.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


ROWS = [contact("S1", "2030-01-01T00:00:00+00:00", "2030-01-01T00:55:00+00:00", "2030-01-01T01:15:00+00:00",
                "2030-01-01T01:30:00+00:00", 150.0),
        contact("S2", "2030-01-01T05:00:00+00:00", "2030-01-01T05:55:00+00:00", "2030-01-01T06:05:00+00:00",
                "2030-01-01T06:20:00+00:00", 150.0, after=200.0)]


def params(**ov):
    return rf.load_parameters({k: v for k, v in {**LINK, **ov}.items()}, use_hga_reference=False)


class TestFormulas(unittest.TestCase):
    def setUp(self):
        self.p = params()
        contacts = [dict(r) for r in ROWS]
        self.res = rf.budget(contacts, self.p, GEN, OVH, 256000)

    def test_required_rate_matches_closed_form(self):
        c = self.res["contacts"][0]
        net = 150e6 / (20 * 60) + GEN
        self.assertAlmostEqual(c["required_net_bps"], net, places=3)
        self.assertAlmostEqual(c["required_gross_bps"], net / 0.8, places=3)

    def test_rf_power_dc_heat_and_energy_match_link_budget(self):
        d = self.res["design"]
        gross = d["driving_contact"]["required_gross_bps"]
        b = evaluate_link(dict(distance_km=405000, frequency_hz=8.4e9, tx_gain_dbi=d["effective_gain_dbi"],
                               rx_gt_db_per_k=45, data_rate_bps=gross, required_ebn0_db=6, losses_db=4, margin_db=3))
        self.assertAlmostEqual(d["rf_power_w"], b["minimum_tx_rf_w_with_design_margin"], places=6)
        self.assertAlmostEqual(d["tx_dc_w"], d["rf_power_w"] / 0.35 + 8, places=9)
        self.assertAlmostEqual(d["tx_heat_w"], d["tx_dc_w"] - d["rf_power_w"], places=9)
        first = self.res["contacts"][0]
        self.assertAlmostEqual(first["energy_tx_wh"], d["tx_dc_w"] * 20 / 60, places=9)
        self.assertAlmostEqual(first["heat_tx_wh"], d["tx_heat_w"] * 20 / 60, places=9)

    def test_design_is_driven_by_the_most_demanding_contact(self):
        d = self.res["design"]["driving_contact"]
        self.assertEqual(d["satellite"], "S2")          # 150 Mbit in 10 min needs the highest rate
        self.assertIn("visibility window or horizon", d["limited_by"])
        rates = [c["required_gross_bps"] for c in self.res["contacts"]]
        self.assertAlmostEqual(self.res["requirements"]["max_required_gross_bps"], max(rates))
        for c in self.res["contacts"]:
            self.assertGreaterEqual(c["link_margin_db_at_design_point"], -1e-9)
        self.assertAlmostEqual(next(c for c in self.res["contacts"] if c["driving"])["link_margin_db_at_design_point"], 0.0, places=6)

    def test_power_following_rate_never_exceeds_constant_power(self):
        for c in self.res["contacts"]:
            self.assertLessEqual(c["energy_tx_wh_if_power_follows_rate"], c["energy_tx_wh"] + 1e-12)

    def test_scheduler_rate_design_point(self):
        alt = self.res["design_at_scheduler_rate"]
        d = self.res["design"]
        self.assertEqual(alt["gross_bps"], 256000)
        expected = 10 ** ((alt["required_eirp_dbw"] - d["effective_gain_dbi"]) / 10)
        self.assertAlmostEqual(alt["rf_power_w"], expected, places=9)

    def test_no_mass_and_one_design_diameter_only(self):
        text = json.dumps(self.res, default=str).lower()
        self.assertNotIn('"mass', text)
        self.assertIn("antenna mass", " ".join(self.res["excluded"]))
        self.assertEqual({self.res["design"]["diameter_m"]}, {0.38})


class TestModes(unittest.TestCase):
    def test_rf_power_cap_solves_the_diameter_and_round_trips(self):
        capped = rf.budget([dict(r) for r in ROWS], params(diameter_m=None, max_tx_rf_w=0.2), GEN, OVH)
        self.assertEqual(capped["design"]["mode"], "RF_POWER_CAP_GIVEN_DIAMETER_SOLVED")
        d = capped["design"]
        self.assertLessEqual(d["rf_power_w"], 0.2 * (1 + 1e-6))
        self.assertAlmostEqual(d["rf_power_w"], 0.2, delta=2e-4)           # minimal diameter sits on the cap
        back = rf.budget([dict(r) for r in ROWS], params(diameter_m=d["diameter_m"]), GEN, OVH)
        self.assertAlmostEqual(back["design"]["rf_power_w"], d["rf_power_w"], places=6)
        tighter = rf.budget([dict(r) for r in ROWS], params(diameter_m=None, max_tx_rf_w=0.1), GEN, OVH)
        self.assertGreater(tighter["design"]["diameter_m"], d["diameter_m"])
        self.assertTrue(capped["design"]["within_rf_cap"])

    def test_infeasible_cap_is_reported(self):
        res = rf.budget([dict(r) for r in ROWS], params(diameter_m=None, max_tx_rf_w=1e-12), GEN, OVH)
        self.assertEqual(res["status"], "NO_FEASIBLE_APERTURE_FOR_RF_POWER_CAP")

    def test_missing_constraint_is_identified(self):
        res = rf.budget([dict(r) for r in ROWS], params(diameter_m=None), GEN, OVH)
        self.assertEqual(res["status"], "MISSING_PARAMETERS")
        self.assertTrue(any("diameter_m or max_tx_rf_w" in m for m in res["missing_parameters"]))
        self.assertIn("required_eirp_dbw", res["design"])           # requirement still computed

    def test_missing_link_parameter_is_identified(self):
        p = params()
        p["values"]["required_ebn0_db"] = None
        res = rf.budget([dict(r) for r in ROWS], p, GEN, OVH)
        self.assertEqual(res["status"], "MISSING_PARAMETERS")
        self.assertIn("required_ebn0_db", res["missing_parameters"])
        self.assertEqual(res["contacts"], [])

    def test_missing_electrical_inputs_do_not_invent_power(self):
        p = params()
        p["values"]["pa_efficiency"] = None
        res = rf.budget([dict(r) for r in ROWS], p, GEN, OVH)
        self.assertIsNone(res["design"]["tx_dc_w"])
        self.assertIsNone(res["totals"])

    def test_invalid_parameters_rejected(self):
        for bad in (dict(max_tx_rf_w=-1), dict(aperture_efficiency=1.5), dict(pa_efficiency=0), dict(losses_db=-1)):
            with self.assertRaises(ValueError):
                params(**bad)
        with self.assertRaises(ValueError):
            rf.load_parameters({"unknown_key": 1})


class TestInputs(unittest.TestCase):
    def test_only_assigned_contacts_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(rf.load_assigned_contacts(tmp)[1], "MISSING_ASSIGNED_CONTACTS")
            write_contacts(tmp, [contact("S1", "2030-01-01T00:00:00+00:00", "2030-01-01T00:55:00+00:00",
                                         "2030-01-01T01:15:00+00:00", "2030-01-01T01:30:00+00:00", 10, status="FITS_VISIBILITY_ONLY_NOT_ALLOCATED")])
            self.assertEqual(rf.load_assigned_contacts(tmp)[1], "NOT_ASSIGNED_CONTACTS")
            res = rf.run(tmp, generation_bps=GEN, overhead=OVH, make_figures=False)
            self.assertEqual(res["status"], "NOT_ASSIGNED_CONTACTS")
            self.assertEqual(res["contacts"], [])

    def test_outdated_file_without_the_needed_columns_is_reported_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "assigned_contacts.csv").write_text(
                "satellite,station,start_utc,end_utc,status\nS1,A,2030-01-01T00:00:00+00:00,2030-01-01T01:00:00+00:00,%s\n" % rf.ASSIGNED,
                encoding="utf-8")
            res = rf.run(tmp, generation_bps=GEN, overhead=OVH, make_figures=False)
            self.assertEqual(res["status"], "ASSIGNED_CONTACTS_MISSING_COLUMNS_REGENERATE_PIPELINE")

    def test_no_contacts_with_transmission(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_contacts(tmp, [])
            res = rf.run(tmp, generation_bps=GEN, overhead=OVH, make_figures=False)
            self.assertEqual(res["status"], "NO_ASSIGNED_CONTACTS_WITH_TRANSMISSION")


class TestEnergyByDay(unittest.TestCase):
    def test_contact_across_midnight_is_split_by_utc_day(self):
        row = contact("S1", "2030-01-01T22:00:00+00:00", "2030-01-01T23:00:00+00:00", "2030-01-02T01:00:00+00:00",
                      "2030-01-02T01:15:00+00:00", 100.0)
        res = rf.budget([row], params(), GEN, OVH)
        days = {e["date_utc"]: e for e in res["energy_by_day"]}
        self.assertEqual(set(days), {"2030-01-01", "2030-01-02"})
        self.assertAlmostEqual(days["2030-01-01"]["tx_hours"], 1.0)
        self.assertAlmostEqual(days["2030-01-02"]["tx_hours"], 1.0)
        self.assertAlmostEqual(sum(e["energy_tx_wh"] for e in res["energy_by_day"]), res["contacts"][0]["energy_tx_wh"], places=5)


class TestCoherence(unittest.TestCase):
    def checks(self, **ov):
        p = params(**ov)
        res = rf.budget([dict(r) for r in ROWS], p, GEN, OVH, 256000)
        return {c["id"]: c for c in rf.coherence(res, p)}, res, p

    def test_eps_and_thermal_pass_and_fail_against_allocations(self):
        ok, *_ = self.checks(active_dc_allowance_w=100, thermal_allowance_w=100)
        self.assertEqual(ok["EPS-1"]["status"], "PASS")
        self.assertEqual(ok["TCS-1"]["status"], "PASS")
        bad, *_ = self.checks(active_dc_allowance_w=1, thermal_allowance_w=1)
        self.assertEqual(bad["EPS-1"]["status"], "FAIL")
        self.assertEqual(bad["TCS-1"]["status"], "FAIL")

    def test_gimbal_placeholder_is_added_to_the_eps_check(self):
        c, res, _ = self.checks(gimbal_power_w=2, active_dc_allowance_w=100)
        self.assertAlmostEqual(c["EPS-1"]["value"], res["design"]["tx_dc_w"] + 2, places=2)

    def test_pending_items_are_not_marked_as_passed(self):
        c, *_ = self.checks()
        for cid in ("TCS-2", "ADCS-2", "EPS-3", "EPS-4", "RF-2"):
            self.assertEqual(c[cid]["status"], "PENDING")

    def test_eps_budget_assumption_mismatch_is_flagged(self):
        c, *_ = self.checks()
        self.assertEqual(c["EPS-2"]["status"], "WARNING")

    def test_rate_consistency_with_scheduler(self):
        c, res, _ = self.checks()
        self.assertEqual(c["DSN-1"]["status"], "FAIL")              # 150 Mbit in 10 min needs more than 256 kbps
        p = params()
        res2 = rf.budget([dict(ROWS[0])], p, GEN, OVH, 256000)
        self.assertEqual({c["id"]: c for c in rf.coherence(res2, p)}["DSN-1"]["status"], "PASS")

    def test_parameter_conflicts_quantify_the_effect(self):
        p = params()
        res = rf.budget([dict(r) for r in ROWS], p, GEN, OVH)
        conf = {c["parameter"]: c for c in rf.parameter_conflicts(res, p)}
        self.assertAlmostEqual(conf["required_ebn0_db"]["change_db"], 4.0, places=6)       # 10 dB vs 6 dB
        self.assertAlmostEqual(conf["losses_db"]["change_db"], -1.0, places=6)
        self.assertAlmostEqual(conf["rx_gt_db_per_k"]["change_db"], 5.0, places=6)
        self.assertIn("aperture_efficiency", conf)

    def test_no_dc_means_a_single_pending_check(self):
        p = params()
        p["values"]["pa_efficiency"] = None
        res = rf.budget([dict(r) for r in ROWS], p, GEN, OVH)
        self.assertEqual([c["id"] for c in rf.coherence(res, p)], ["RF-0"])


class TestPipelineChain(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "p"
        dsn_pipeline.run(output_dir=cls.out, downlink_bps=256000, telemetry_profile="scenario", make_plots=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_reference_scenario_uses_only_the_assigned_contacts(self):
        res = rf.run(self.out, make_figures=False)
        with (self.out / "assigned_contacts.csv").open(newline="", encoding="utf-8") as f:
            assigned = list(csv.DictReader(f))
        self.assertEqual(res["status"], rf.STATUS)
        self.assertEqual(len(res["contacts"]), len(assigned))
        self.assertEqual({(c["satellite"], c["start_utc"]) for c in res["contacts"]},
                         {(a["satellite"], a["start_utc"]) for a in assigned})
        self.assertEqual(res["design"]["diameter_m"], 0.38)
        self.assertIn("HYPOTHETICAL_NOT_SELECTED", res["parameters"]["diameter_m"]["source"])
        for name in ("rf_budget_summary.json", "rf_budget_by_contact.csv", "rf_budget_energy_by_day.csv",
                     "rf_coherence_checks.csv", "rf_parameter_conflicts.csv"):
            self.assertTrue((self.out / name).exists(), name)

    def test_user_supplied_scenario_changes_the_result(self):
        a = rf.run(self.out, overrides={"diameter_m": 0.30}, make_figures=False)
        b = rf.run(self.out, overrides={"diameter_m": 0.60}, make_figures=False)
        self.assertGreater(a["design"]["rf_power_w"], b["design"]["rf_power_w"])
        self.assertIn("user override", a["parameters"]["diameter_m"]["source"])
        capped = rf.run(self.out, overrides={"max_tx_rf_w": 0.15, "diameter_m": None}, use_hga_reference=False, make_figures=False)
        self.assertEqual(capped["design"]["mode"], "RF_POWER_CAP_GIVEN_DIAMETER_SOLVED")

    def test_no_reference_and_no_constraint_reports_the_missing_parameter(self):
        res = rf.run(self.out, use_hga_reference=False, make_figures=False)
        self.assertEqual(res["status"], "MISSING_PARAMETERS")
        self.assertTrue(any("diameter_m or max_tx_rf_w" in m for m in res["missing_parameters"]))

    def test_integrated_requirements_wrapper(self):
        (self.out / "telemetry_generation.json").write_text(json.dumps({"total_rate_bps_per_spacecraft": GEN}), encoding="utf-8")
        res = build(self.out)
        self.assertEqual(res["source"], "assigned_contacts_from_dsn_scheduler")
        self.assertEqual(res["cases"], len(list(csv.DictReader((self.out / "assigned_contacts.csv").open(encoding="utf-8")))))

    def test_figures_are_generated_when_matplotlib_is_available(self):
        res = rf.run(self.out, make_figures=True)
        status = res["figures"]["status"]
        if status == "OK":
            names = {Path(f).name for f in res["figures"]["files"]}
            self.assertEqual(names, {"rf_rate_and_power_by_contact.png", "rf_energy_by_contact_and_day.png",
                                     "rf_power_vs_allowances.png"})
        else:
            self.assertEqual(status, "MATPLOTLIB_NOT_INSTALLED")


if __name__ == "__main__":
    unittest.main()
