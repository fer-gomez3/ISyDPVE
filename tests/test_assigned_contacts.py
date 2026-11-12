"""Assigned contacts are the single source of truth; data conservation; explicit failures.

Synthetic numbers are illustrative; they test accounting and failure reporting,
not any engineering value.
"""
import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ttc import dsn_pipeline
from ttc.dsn_scheduler import schedule_contacts
from ttc.ground_delivery import simulate
from ttc.integrated_requirements import build
from ttc.memory_queues import QueueObserver, load_memory_config, write_outputs

T0 = datetime(2030, 1, 1, tzinfo=timezone.utc)
HOURS = 48
PREP, TEAR, MINTX = 3300.0, 900.0, 300.0
STREAMS = [
    {"name": "aocs", "rate_bps": 1500.0, "priority": 5, "deadline_hours": 6.0},
    {"name": "thermal", "rate_bps": 400.0, "priority": 3, "deadline_hours": 24.0},
    {"name": "eps", "rate_bps": 401.74, "priority": 4, "deadline_hours": 12.0},
]


def win(sat, station, h0, h1):
    return {"satellite": sat, "station": station, "start": T0 + timedelta(hours=h0), "end": T0 + timedelta(hours=h1)}


def run_case(windows, streams=STREAMS, cfg=None, geometric=None, cap_h=3.0):
    end = T0 + timedelta(hours=HOURS)
    sched = schedule_contacts(windows, streams, start=T0, end=end, gross_bps=256000, overhead=0.2,
                              prep_s=PREP, teardown_s=TEAR, min_tx_s=MINTX, daily_cap_s=cap_h * 3600,
                              geometric_windows=geometric)
    contacts = sched["contacts"]
    vis = [{"satellite": w["satellite"], "station": w["station"], "start_utc": (geometric or windows)[i]["start"].isoformat(),
            "end_utc": (geometric or windows)[i]["end"].isoformat()} for i, w in enumerate(geometric or windows)]
    grants = [{"satellite": c["satellite"], "station": c["station"], "start_utc": c["tx_start"].isoformat(),
               "end_utc": c["tx_end"].isoformat()} for c in contacts]
    all_sats = sorted({w["satellite"] for w in (geometric or windows)})
    obs = QueueObserver(streams, T0, cfg or load_memory_config(), contacts=contacts,
                        visibility=[{**w} for w in windows], min_tx_s=MINTX, satellites=all_sats)
    delivery = simulate(streams, vis, grants, gross_bps=256000, overhead=0.2, setup_minutes=0, step_seconds=60,
                        start_utc=T0.isoformat(), end_utc=end.isoformat(), observer=obs)
    return sched, delivery, obs, obs.summary(delivery, HOURS)


def codes(summary):
    return {f["code"] for f in summary["requirements"]["failures"]}


class TestNominal(unittest.TestCase):
    def setUp(self):
        self.windows = [win(f"S{i}", "A" if i % 2 else "B", 0, HOURS) for i in range(1, 5)]
        self.sched, self.delivery, self.obs, self.summary = run_case(self.windows)

    def test_conservation_per_satellite_and_subsystem(self):
        cons = self.summary["conservation"]
        self.assertLess(cons["max_abs_residual_mbit"], 1e-6)
        for sat, c in cons["satellites"].items():
            self.assertAlmostEqual(c["initial_mbit"] + c["generated_mbit"], c["downloaded_mbit"] + c["final_mbit"], places=5)
            for n, x in c["by_stream"].items():
                self.assertAlmostEqual(x["initial_mbit"] + x["generated_mbit"], x["downloaded_mbit"] + x["final_mbit"], places=5, msg=f"{sat}/{n}")
        self.assertNotIn("DATA_CONSERVATION_VIOLATION", codes(self.summary))

    def test_every_contact_balances_and_all_downloads_are_attributed(self):
        rows = self.summary["assigned_contacts"]
        self.assertEqual(len(rows), len(self.sched["contacts"]))
        for r in rows:
            self.assertAlmostEqual(r["backlog_at_start_mbit"] + r["generated_during_contact_mbit"],
                                   r["downloaded_mbit"] + r["backlog_after_mbit"], places=5)
            self.assertGreaterEqual(r["useful_tx_minutes"], MINTX / 60 - 1e-9)
        per_sat = {}
        for r in rows:
            per_sat[r["satellite"]] = per_sat.get(r["satellite"], 0.0) + r["downloaded_mbit"]
        for sat, c in self.summary["conservation"]["satellites"].items():
            self.assertAlmostEqual(per_sat.get(sat, 0.0), c["downloaded_mbit"], places=4)
        self.assertNotIn("UNATTRIBUTED_DOWNLOAD", codes(self.summary))

    def test_no_improper_overlap(self):
        for key in ("station", "satellite"):
            for name in {r[key] for r in self.summary["assigned_contacts"]}:
                mine = sorted((r for r in self.summary["assigned_contacts"] if r[key] == name), key=lambda r: r["start_utc"])
                for a, b in zip(mine, mine[1:]):
                    self.assertLessEqual(a["end_utc"], b["start_utc"])
        self.assertFalse({c for c in codes(self.summary) if c.startswith("CONTACT_OVERLAP")})

    def test_unmet_deadlines_are_reported_as_failures(self):
        # 3 h/day cannot hold 6 h / 12 h / 24 h ages for four satellites over 48 h
        self.assertEqual(self.summary["requirements"]["status"], "REQUIREMENTS_NOT_MET")
        self.assertIn("DEADLINE_MISSED", codes(self.summary))
        f = next(f for f in self.summary["requirements"]["failures"] if f["code"] == "DEADLINE_MISSED")
        self.assertTrue(f["satellite"] and f["stream"] and f["first_violation_utc"])


class TestOverlapDetection(unittest.TestCase):
    def test_overlapping_contacts_are_flagged(self):
        bad = [{"satellite": "S1", "station": "A", "start": T0, "end": T0 + timedelta(hours=2),
                "tx_start": T0 + timedelta(minutes=55), "tx_end": T0 + timedelta(hours=1, minutes=45)},
               {"satellite": "S2", "station": "A", "start": T0 + timedelta(hours=1), "end": T0 + timedelta(hours=3),
                "tx_start": T0 + timedelta(hours=1, minutes=55), "tx_end": T0 + timedelta(hours=2, minutes=45)}]
        obs = QueueObserver(STREAMS, T0, load_memory_config(), contacts=bad)
        grants = [{"satellite": c["satellite"], "station": c["station"], "start_utc": c["tx_start"].isoformat(),
                   "end_utc": c["tx_end"].isoformat()} for c in bad]
        vis = [{"satellite": s, "station": "A", "start_utc": T0.isoformat(), "end_utc": (T0 + timedelta(hours=6)).isoformat()} for s in ("S1", "S2")]
        d = simulate(STREAMS, vis, grants, gross_bps=256000, overhead=0.2, setup_minutes=0, step_seconds=60,
                     start_utc=T0.isoformat(), end_utc=(T0 + timedelta(hours=6)).isoformat(), observer=obs)
        self.assertIn("CONTACT_OVERLAP_STATION", codes(obs.summary(d, 6)))


class TestBurst(unittest.TestCase):
    def test_burst_overflows_memory_and_is_a_failure_not_a_silent_drop(self):
        burst = [{**s, "rate_bps": s["rate_bps"] * 40} for s in STREAMS]       # illustrative burst multiplier
        windows = [win("S1", "A", 0, HOURS)]
        cfg = {**load_memory_config(), "capacity_mbit": 100.0, "usable_mbit": 85.0, "reserve_mbit": 15.0}
        sched, delivery, obs, summary = run_case(windows, streams=burst, cfg=cfg)
        self.assertIn("MEMORY_OVERFLOW", codes(summary))
        f = next(f for f in summary["requirements"]["failures"] if f["code"] == "MEMORY_OVERFLOW")
        self.assertGreater(f["overflow_mbit"], 0)
        self.assertNotIn("DATA_CONSERVATION_VIOLATION", codes(summary))     # accounting stays exact
        self.assertLess(summary["conservation"]["max_abs_residual_mbit"], 1e-6)

    def test_reserve_use_is_distinct_from_overflow(self):
        windows = [win("S1", "A", 0, HOURS)]
        cfg = {**load_memory_config(), "capacity_mbit": 150.0, "usable_mbit": 127.5, "reserve_mbit": 22.5}
        _, _, _, summary = run_case(windows, cfg=cfg)
        self.assertTrue({"MEMORY_RESERVE_EXCEEDED", "MEMORY_OVERFLOW"} & codes(summary))


class TestStationUnavailableAndNoContacts(unittest.TestCase):
    def test_station_unavailable_leaves_satellite_uncovered_and_says_so(self):
        geometric = [win("S1", "A", 0, HOURS), win("S2", "B", 0, HOURS)]
        offered = [win("S1", "A", 0, HOURS)]                                  # station B down
        sched, _, _, summary = run_case(offered, geometric=geometric)
        self.assertIn("NO_CONTACT", codes(summary))
        nc = [f for f in summary["requirements"]["failures"] if f["code"] == "NO_CONTACT"]
        self.assertEqual([f["satellite"] for f in nc], ["S2"])
        self.assertIn("STATION_AVAILABILITY", {f["constraint"] for f in sched["diagnostics"]["coverage"]["analysis"]["binding_constraints"]})
        self.assertLess(summary["conservation"]["max_abs_residual_mbit"], 1e-6)

    def test_no_contacts_at_all(self):
        sched, delivery, _, summary = run_case([], geometric=[win("S1", "A", 0, HOURS), win("S2", "B", 0, HOURS)])
        self.assertEqual(summary["assigned_contacts"], [])
        self.assertEqual({f["satellite"] for f in summary["requirements"]["failures"] if f["code"] == "NO_CONTACT"}, {"S1", "S2"})
        for c in summary["conservation"]["satellites"].values():
            self.assertEqual(c["downloaded_mbit"], 0.0)
            self.assertAlmostEqual(c["generated_mbit"], c["final_mbit"], places=5)


class TestSingleSourceOfTruth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "p"
        cls.result = dsn_pipeline.run(output_dir=cls.out, downlink_bps=256000, telemetry_profile="scenario", make_plots=False)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rows(self, name):
        with (self.out / name).open(newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_requested_durations_are_exactly_the_scheduled_contacts(self):
        sched = self.rows("candidate_schedule.csv")
        req = self.rows("requested_contact_durations.csv")
        self.assertEqual(len(req), len(sched))
        self.assertEqual({(r["satellite"], r["station"], r["start"]) for r in sched},
                         {(r["satellite"], r["station"], r["reservation_start_utc"]) for r in req})
        for r in req:
            self.assertIn("ASSIGNED_CONTACTS", r["source"])
        self.assertEqual(len(self.rows("assigned_contacts.csv")), len(sched))

    def test_candidate_windows_are_kept_separate_and_labelled(self):
        cand = self.rows("candidate_window_requests.csv")
        self.assertGreater(len(cand), len(self.rows("candidate_schedule.csv")))
        self.assertTrue(all(r["status"] in ("FITS_VISIBILITY_ONLY_NOT_ALLOCATED", "NOT_FEASIBLE_IN_WINDOW") for r in cand))
        self.assertIn("NOT reservations", self.result["contact_duration_output"]["candidate_windows_interpretation"])

    def test_summary_carries_conservation_and_requirements(self):
        self.assertLess(self.result["data_conservation"]["max_abs_residual_mbit"], 1e-6)
        self.assertEqual(self.result["requirements"]["status"], "REQUIREMENTS_NOT_MET")
        self.assertEqual(set(self.result["requirements"]["counts_by_code"]), {"DEADLINE_MISSED"})

    def test_antenna_sizing_uses_only_assigned_contacts(self):
        gen = {"total_rate_bps_per_spacecraft": 2301.74}
        (self.out / "telemetry_generation.json").write_text(json.dumps(gen), encoding="utf-8")
        res = build(self.out)
        self.assertEqual(res["source"], "assigned_contacts_from_dsn_scheduler")
        self.assertEqual(res["cases"], len(self.rows("assigned_contacts.csv")))
        # a candidate-style file (no assigned columns) must not be sized
        legacy = Path(self.tmp.name) / "legacy"
        legacy.mkdir()
        (legacy / "telemetry_generation.json").write_text(json.dumps(gen), encoding="utf-8")
        (legacy / "requested_contact_durations.csv").write_text(
            "satellite,station,visibility_start_utc,backlog_at_start_mbit,required_useful_tx_minutes\nS1,A,2030-01-01,10,5\n", encoding="utf-8")
        self.assertEqual(build(legacy)["status"], "MISSING_CONTACT_DURATIONS")


class TestPipelineWithUnavailableStations(unittest.TestCase):
    def test_goldstone_down_is_not_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = dsn_pipeline.run(output_dir=Path(tmp) / "x", availability={"Goldstone": []}, make_plots=False)
            with (Path(tmp) / "x" / "assigned_contacts.csv").open(newline="", encoding="utf-8") as f:
                self.assertNotIn("Goldstone", {row["station"] for row in csv.DictReader(f)})
            self.assertLess(r["data_conservation"]["max_abs_residual_mbit"], 1e-6)

    def test_all_stations_down_reports_no_contact_for_every_satellite(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = dsn_pipeline.run(output_dir=Path(tmp) / "x", availability={"Goldstone": [], "Madrid": [], "Canberra": []}, make_plots=False)
            self.assertEqual(r["contact_duration_output"]["count"], 0)
            nc = [f for f in r["requirements"]["failures"] if f["code"] == "NO_CONTACT"]
            self.assertEqual(len(nc), 8)
            self.assertLess(r["data_conservation"]["max_abs_residual_mbit"], 1e-6)


class TestPDRData(unittest.TestCase):
    def test_pdr_loader_and_figures_come_from_results(self):
        from ttc import pdr_data
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "r"
            dsn_pipeline.run(output_dir=out, telemetry_profile="scenario", make_plots=False)
            data = pdr_data.load(out)
            self.assertEqual(len(data["assigned_contacts"]), len(data["summary"]["assigned_contacts"]))
            self.assertTrue(data["memory_curves"] and data["downloaded_by_subsystem"])
            self.assertIn("not confirmed", data["caveat"])
            figs = pdr_data.plot_figures(out)
            if figs["status"] == "OK":
                names = {Path(f).name for f in figs["files"]}
                self.assertIn("downloaded_by_subsystem.png", names)
                self.assertIn("dsn_contacts_used.png", names)
                self.assertEqual(sum(n.startswith("memory_by_subsystem_") for n in names), 8)
            else:
                self.assertEqual(figs["status"], "MATPLOTLIB_NOT_INSTALLED")
        self.assertEqual(pdr_data.plot_figures("/nonexistent_dir_xyz")["status"], "NO_RESULTS")


if __name__ == "__main__":
    unittest.main()
