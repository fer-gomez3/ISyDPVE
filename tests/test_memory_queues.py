"""Logical per-subsystem queues inside the shared OBDH memory (accounting only)."""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ttc.ground_delivery import simulate
from ttc.memory_queues import QueueObserver, load_memory_config, write_outputs

T0 = datetime(2030, 1, 1, tzinfo=timezone.utc)
STREAMS = [
    {"name": "aocs", "rate_bps": 1500.0, "priority": 5, "deadline_hours": 6.0},
    {"name": "thermal", "rate_bps": 400.0, "priority": 3, "deadline_hours": 24.0},
    {"name": "eps", "rate_bps": 401.74, "priority": 4, "deadline_hours": 12.0},
]
HOURS = 30


def run(grants, observer=None):
    vis = [{"satellite": s, "station": "A", "start_utc": T0.isoformat(),
            "end_utc": (T0 + timedelta(hours=HOURS)).isoformat()} for s in ("S1", "S2")]
    return simulate(STREAMS, vis, grants, gross_bps=256000, overhead=0.2, setup_minutes=0,
                    step_seconds=60, start_utc=T0.isoformat(),
                    end_utc=(T0 + timedelta(hours=HOURS)).isoformat(), observer=observer)


def grant(sat, h0, minutes):
    a = T0 + timedelta(hours=h0)
    return {"satellite": sat, "station": "A", "start_utc": a.isoformat(),
            "end_utc": (a + timedelta(minutes=minutes)).isoformat()}


class TestMemoryConfig(unittest.TestCase):
    def test_scenario_values(self):
        c = load_memory_config()
        self.assertEqual(c["capacity_mbit"], 1024)
        self.assertAlmostEqual(c["usable_mbit"], 870.4)
        self.assertAlmostEqual(c["reserve_mbit"], 153.6)
        self.assertEqual(c["warning_thresholds"], [0.7, 0.85, 0.95])
        self.assertEqual(c["proactive_trigger_fraction"], 0.65)

    def test_invalid_config_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "c.json"
            p.write_text(json.dumps({"memory_capacity_mbit_per_satellite": 0, "memory_reserve_fraction": 0.15,
                                     "warning_thresholds": [0.7, 0.85, 0.95], "proactive_trigger_fraction": 0.65}))
            with self.assertRaises(ValueError):
                load_memory_config(p)


class TestQueues(unittest.TestCase):
    def setUp(self):
        self.grants = [grant("S1", 20, 30)]
        self.obs = QueueObserver(STREAMS, T0, load_memory_config())
        self.delivery = run(self.grants, self.obs)
        self.summary = self.obs.summary(self.delivery, HOURS)

    def test_observer_does_not_change_the_simulation(self):
        plain = run(self.grants)
        self.assertEqual(plain["satellites"], self.delivery["satellites"])

    def test_queues_add_up_to_the_shared_memory_and_to_conservation(self):
        for sat, v in self.summary["satellites"].items():
            at_peak = sum(x["queue_mbit_at_total_peak"] for x in v["by_stream"].values())
            self.assertAlmostEqual(at_peak, v["peak_total_mbit"], delta=1e-3)
            shares = sum(x["share_of_peak_occupancy"] for x in v["by_stream"].values())
            self.assertAlmostEqual(shares, 1.0, delta=1e-3)
            for x in v["by_stream"].values():
                self.assertAlmostEqual(x["generated_mbit"], x["delivered_mbit"] + x["remaining_mbit"], delta=1e-3)

    def test_each_satellite_has_its_own_memory(self):
        s1, s2 = self.summary["satellites"]["S1"], self.summary["satellites"]["S2"]
        self.assertLess(s1["by_stream"]["aocs"]["delivered_mbit"] + 1e-9, 1e9)
        self.assertGreater(s1["by_stream"]["aocs"]["delivered_mbit"], 0)
        self.assertEqual(s2["by_stream"]["aocs"]["delivered_mbit"], 0)

    def test_generation_figures(self):
        g = self.summary["generation"]
        self.assertAlmostEqual(g["per_satellite_bps"], 2301.74, places=2)
        self.assertAlmostEqual(g["per_satellite_mbit_per_day"], 198.87, places=2)
        self.assertEqual(g["constellation_satellites"], 2)
        self.assertAlmostEqual(g["constellation_bps"], 2 * 2301.74, places=1)
        self.assertIn("not downloaded", g["note"])

    def test_download_order_is_deadline_then_priority(self):
        # a short contact cannot drain everything: AOCS (6 h) must leave before thermal (24 h)
        d = run([grant("S1", 20, 2)])["satellites"]["S1"]["by_stream"]   # ~24.6 Mbit vs ~165 Mbit queued
        self.assertGreater(d["aocs"]["delivered_bits"], 0)
        self.assertEqual(d["thermal"]["delivered_bits"], 0)

    def test_status_and_model_statements(self):
        self.assertIn("no physical partitions", self.summary["model"])
        self.assertIn("not approved requirements", self.summary["memory"]["note"])

    def test_threshold_crossings_follow_the_configuration(self):
        none = QueueObserver(STREAMS, T0, {**load_memory_config(), "capacity_mbit": 1e9, "usable_mbit": 1e9})
        run([], none)
        self.assertEqual(none.summary(run([]), HOURS)["satellites"]["S1"]["first_threshold_crossing_utc"], {})
        tiny = QueueObserver(STREAMS, T0, {**load_memory_config(), "capacity_mbit": 10, "usable_mbit": 8.5})
        run([], tiny)
        s = tiny.summary(run([]), HOURS)["satellites"]["S1"]
        self.assertTrue(s["usable_limit_exceeded"])
        order = ["proactive_trigger", "watch", "urgent", "critical", "usable_limit"]
        times = [s["first_threshold_crossing_utc"][k] for k in ("proactive_trigger", "watch", "urgent", "critical")]
        self.assertEqual(times, sorted(times))
        self.assertIn(order[0], s["first_threshold_crossing_utc"])

    def test_outputs_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_outputs(self.obs, self.delivery, HOURS, tmp)
            self.assertTrue((Path(tmp) / "memory_queues.csv").exists())
            data = json.loads((Path(tmp) / "memory_queues_summary.json").read_text())
            self.assertEqual(set(data["satellites"]), {"S1", "S2"})


if __name__ == "__main__":
    unittest.main()
