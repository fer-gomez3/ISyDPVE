"""End-to-end checks of the DSN -> OBDH pipeline and OBDH report.

They validate invariants (data conservation, no overlapping contacts, downloads
only during contacts, output files) and do not assert any engineering value.
"""
import csv
import json
import os
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from ttc import dsn_pipeline, obdh_report
from ttc.contact_analysis import load_contacts

ROOT = Path(__file__).resolve().parents[1]
EPS = 1e-6  # Mbit


class TestDSNPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name) / "dsn"
        # Run from another directory to prove the default paths do not depend on cwd.
        cls.old = os.getcwd()
        os.chdir(cls.tmp.name)
        try:
            cls.result = dsn_pipeline.run(output_dir=cls.out, downlink_bps=256000)
        finally:
            os.chdir(cls.old)
        cls.contacts = load_contacts(ROOT / "data" / "contacts_master.csv")
        with (cls.out / "candidate_schedule.csv").open(newline="", encoding="utf-8") as f:
            cls.schedule = [dict(r, start=datetime.fromisoformat(r["start"]),
                                 end=datetime.fromisoformat(r["end"])) for r in csv.DictReader(f)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_outputs_exist_and_parse(self):
        self.assertTrue((self.out / "summary.json").exists())
        self.assertTrue((self.out / "candidate_schedule.csv").exists())
        summary = json.loads((self.out / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["scenario_downlink_gross_bps"], 256000)
        self.assertEqual(summary["status"], "PRELIMINARY_NOT_DSN_BOOKED")
        sats = sorted({c["satellite"] for c in self.contacts})
        self.assertEqual(sorted(summary["satellites"]), sats)
        for sat in sats:
            self.assertTrue((self.out / f"{sat}_obdh.csv").exists())

    def test_data_conservation(self):
        for sat, r in self.result["satellites"].items():
            self.assertAlmostEqual(
                r["generated_mbit"], r["transmitted_mbit"] + r["final_buffer_mbit"],
                delta=EPS, msg=sat)
            self.assertGreaterEqual(r["final_buffer_mbit"], -EPS)

    def test_no_overlapping_contacts(self):
        for key in ("station", "satellite"):
            for name in {c[key] for c in self.schedule}:
                rows = sorted((c for c in self.schedule if c[key] == name),
                              key=lambda c: c["start"])
                for a, b in zip(rows, rows[1:]):
                    self.assertLessEqual(a["end"], b["start"], f"{key}={name}")

    def test_downloads_only_during_contacts_and_within_capacity(self):
        cap_bps = 256000 * (1 - 0.2)
        for sat in self.result["satellites"]:
            with (self.out / f"{sat}_obdh.csv").open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            previous = None
            total = 0.0
            for r in rows:
                sent = float(r["downlinked_interval_mbit"])
                total += sent
                if r["contact_active"] != "True":
                    self.assertEqual(sent, 0.0, f"{sat} downlink outside contact")
                if previous is not None and sent > 0:
                    from datetime import datetime
                    seconds = (datetime.fromisoformat(r["time_utc"]) -
                               datetime.fromisoformat(previous)).total_seconds()
                    self.assertLessEqual(sent * 1e6, cap_bps * seconds * (1 + 1e-9) + 1e-3)
                previous = r["time_utc"]
            self.assertAlmostEqual(total, self.result["satellites"][sat]["transmitted_mbit"], delta=1e-4)

    def test_every_contact_has_positive_duration_and_known_station(self):
        stations = {c["station"] for c in self.contacts}
        for c in self.schedule:
            self.assertGreater(c["end"], c["start"])
            self.assertIn(c["station"], stations)
            self.assertEqual(c["status"], "HYPOTHETICAL_ALLOCATION_NOT_DSN_BOOKING")

    def test_all_satellites_served_and_daily_budget_respected(self):
        sats = {c["satellite"] for c in self.contacts}
        self.assertEqual({c["satellite"] for c in self.schedule}, sats)
        per_day = {}
        for c in self.schedule:
            a = c["start"]
            while a < c["end"]:
                nxt = min(c["end"], datetime.combine(a.date() + timedelta(days=1),
                                                     datetime.min.time(), tzinfo=a.tzinfo))
                per_day[a.date()] = per_day.get(a.date(), 0) + (nxt - a).total_seconds()
                a = nxt
        for day, secs in per_day.items():
            self.assertLessEqual(secs, 3 * 3600 + 1e-6, str(day))
        summary = json.loads((self.out / "summary.json").read_text(encoding="utf-8"))
        self.assertIn("allocation", summary)
        self.assertIn("deadline_explanation", summary)
        self.assertIn("NOT confirmed", summary["allocation"]["visibility_note"])


class TestOBDHReport(unittest.TestCase):
    def test_report_generates_summary_and_timelines(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary = obdh_report.run(output_dir=Path(tmp) / "obdh", downlink_bps=256000)
            self.assertTrue((Path(tmp) / "obdh" / "summary.json").exists())
            self.assertEqual(len(summary["satellites"]), 8)
            for sat, r in summary["satellites"].items():
                self.assertAlmostEqual(
                    r["generated_mbit"], r["transmitted_mbit"] + r["final_buffer_mbit"],
                    delta=EPS, msg=sat)
                self.assertTrue((Path(tmp) / "obdh" / f"{sat}_timeline.csv").exists())


if __name__ == "__main__":
    unittest.main()
