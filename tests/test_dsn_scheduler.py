"""Unified DSN scheduler: coverage, constraints, diagnostics and determinism.

Synthetic cases use illustrative numbers only; they check that constraints are
respected and that failures are explained, not any engineering value.
"""
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ttc.contact_analysis import load_contacts
from ttc.dsn_allocator import allocate
from ttc.dsn_scheduler import schedule_contacts, explain_unmet_deadlines

ROOT = Path(__file__).resolve().parents[1]
T0 = datetime(2030, 1, 1, tzinfo=timezone.utc)
PREP, TEAR, MINTX = 3300.0, 900.0, 300.0      # 55 min + 15 min overhead, 5 min useful
RES_MIN = PREP + TEAR + MINTX                  # 75 min
LOW = [{"name": "hk", "rate_bps": 2301.74, "priority": 3, "deadline_hours": 24.0}]
HIGH = [{"name": "hk", "rate_bps": 100000.0, "priority": 5, "deadline_hours": 6.0}]


def win(sat, station, start_h, end_h):
    return {"satellite": sat, "station": station,
            "start": T0 + timedelta(hours=start_h), "end": T0 + timedelta(hours=end_h)}


def sched(windows, streams=LOW, hours=24, cap_h=3.0, geometric=None, **kw):
    return schedule_contacts(windows, streams, start=T0, end=T0 + timedelta(hours=hours),
                             gross_bps=256000, overhead=0.2, prep_s=PREP, teardown_s=TEAR,
                             min_tx_s=MINTX, daily_cap_s=cap_h * 3600, geometric_windows=geometric, **kw)


def check_invariants(test, result, windows, cap_h):
    rows = result["contacts"]
    for key in ("station", "satellite"):
        for name in {r[key] for r in rows}:
            mine = sorted((r for r in rows if r[key] == name), key=lambda r: r["start"])
            for a, b in zip(mine, mine[1:]):
                test.assertLessEqual(a["end"], b["start"], f"overlap on {key}={name}")
    for r in rows:
        test.assertTrue(any(w["satellite"] == r["satellite"] and w["station"] == r["station"] and
                            w["start"] <= r["start"] and r["end"] <= w["end"] for w in windows),
                        "contact outside its visibility window")
        test.assertAlmostEqual(r["usable_seconds"], r["seconds"] - PREP - TEAR, places=3)
        test.assertGreaterEqual(r["usable_seconds"], MINTX - 1e-6)
    per_day = {}
    for r in rows:
        a = r["start"]
        while a < r["end"]:
            nxt = min(r["end"], datetime.combine(a.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc))
            per_day[a.date()] = per_day.get(a.date(), 0) + (nxt - a).total_seconds()
            a = nxt
    for day, secs in per_day.items():
        test.assertLessEqual(secs, cap_h * 3600 + 1e-6, f"daily budget exceeded on {day}")


class TestEarliestEndTrap(unittest.TestCase):
    """The old criterion drops a satellite whose long window overlaps a short one."""

    def setUp(self):
        self.windows = [win("S1", "A", 0, 10), win("S2", "A", 0, 2)]

    def test_old_criterion_leaves_a_satellite_unserved(self):
        old = allocate(self.windows, None, RES_MIN + 1, 0)
        self.assertEqual({c["satellite"] for c in old}, {"S2"})

    def test_new_scheduler_serves_both(self):
        r = sched(self.windows)
        self.assertEqual({c["satellite"] for c in r["contacts"]}, {"S1", "S2"})
        self.assertTrue(r["diagnostics"]["coverage"]["all_satellites_covered"])
        check_invariants(self, r, self.windows, 3.0)


class TestCoverageGuard(unittest.TestCase):
    def test_late_satellite_is_not_starved_by_early_long_passes(self):
        # Heavy telemetry makes the first satellites ask for very long passes. S3
        # is only visible late. A feasible plan serving all three exists.
        windows = [win("S1", "A", 0, 24), win("S2", "A", 0, 24), win("S3", "A", 19, 24)]
        r = sched(windows, HIGH, cap_h=4.0)
        self.assertEqual(r["diagnostics"]["coverage"]["initial_feasibility"], "FEASIBLE")
        self.assertEqual({c["satellite"] for c in r["contacts"]}, {"S1", "S2", "S3"})
        check_invariants(self, r, windows, 4.0)

    def test_coverage_found_on_real_windows(self):
        contacts = load_contacts(ROOT / "data" / "contacts_master.csv")
        start = min(c["start"] for c in contacts)
        end = max(c["end"] for c in contacts)
        r = schedule_contacts(contacts, LOW, start=start, end=end, gross_bps=256000, overhead=0.2,
                              prep_s=PREP, teardown_s=TEAR, min_tx_s=MINTX, daily_cap_s=3 * 3600)
        self.assertEqual(r["diagnostics"]["coverage"]["initial_feasibility"], "FEASIBLE")
        self.assertEqual(len({c["satellite"] for c in r["contacts"]}), 8)
        check_invariants(self, r, contacts, 3.0)

    def test_deterministic(self):
        windows = [win("S1", "A", 0, 24), win("S2", "B", 0, 24), win("S3", "A", 5, 24)]
        a, b = sched(windows, HIGH, cap_h=4.0), sched(windows, HIGH, cap_h=4.0)
        self.assertEqual(a["contacts"], b["contacts"])


class TestExplainedInfeasibility(unittest.TestCase):
    def constraints(self, r):
        return {f["constraint"] for f in r["diagnostics"]["coverage"]["analysis"]["binding_constraints"]}

    def test_budget_smaller_than_one_minimum_pass(self):
        r = sched([win("S1", "A", 0, 24), win("S2", "B", 0, 24)], cap_h=1.0)
        self.assertEqual(r["contacts"], [])
        self.assertFalse(r["diagnostics"]["coverage"]["all_satellites_covered"])
        self.assertIn("DAILY_BUDGET", self.constraints(r))

    def test_window_shorter_than_minimum_pass_is_geometry(self):
        r = sched([win("S1", "A", 0, 10), win("S2", "B", 0, 1.0)])
        self.assertEqual(r["diagnostics"]["coverage"]["satellites_without_contact"], ["S2"])
        self.assertIn("GEOMETRY", self.constraints(r))
        self.assertEqual({c["satellite"] for c in r["contacts"]}, {"S1"})

    def test_availability_is_separated_from_geometry(self):
        geometric = [win("S1", "A", 0, 10), win("S2", "B", 0, 10)]
        offered = [win("S1", "A", 0, 10), win("S2", "B", 0, 0.5)]
        r = sched(offered, geometric=geometric)
        self.assertIn("STATION_AVAILABILITY", self.constraints(r))
        self.assertNotIn("GEOMETRY", self.constraints(r))

    def test_station_conflict_serves_best_possible_and_says_why(self):
        # one antenna, two satellites, 80 min window each: only one fits
        windows = [win("S1", "A", 0, 80 / 60), win("S2", "A", 0, 80 / 60)]
        r = sched(windows)
        self.assertEqual(r["diagnostics"]["coverage"]["initial_feasibility"], "INFEASIBLE")
        self.assertIn("STATION_CONFLICT", self.constraints(r))
        self.assertEqual(len(r["contacts"]), 1)
        self.assertEqual(len(r["diagnostics"]["coverage"]["satellites_without_contact"]), 1)

    def test_invalid_parameters_rejected(self):
        with self.assertRaises(ValueError):
            sched([win("S1", "A", 0, 10)], hours=-1)
        with self.assertRaises(ValueError):
            schedule_contacts([win("S1", "A", 0, 10)], [], start=T0, end=T0 + timedelta(hours=5),
                              gross_bps=1, overhead=0.2, prep_s=0, teardown_s=0, min_tx_s=1, daily_cap_s=1)


class TestPolicy(unittest.TestCase):
    def test_each_contact_has_a_reason_and_is_not_a_booking(self):
        r = sched([win("S1", "A", 0, 24), win("S2", "B", 0, 24)], HIGH, cap_h=4.0)
        self.assertTrue(r["contacts"])
        for c in r["contacts"]:
            self.assertIn(c["reason"], {"critical_deadline", "equitable_share", "coverage_guard"})
            self.assertEqual(c["status"], "HYPOTHETICAL_ALLOCATION_NOT_DSN_BOOKING")
        self.assertIn("NOT confirmed DSN availability", r["diagnostics"]["visibility_note"])

    def test_larger_budget_never_serves_fewer_satellites(self):
        windows = [win("S1", "A", 0, 24), win("S2", "A", 0, 24), win("S3", "B", 0, 24)]
        small = len({c["satellite"] for c in sched(windows, HIGH, cap_h=2.6)["contacts"]})
        large = len({c["satellite"] for c in sched(windows, HIGH, cap_h=6.0)["contacts"]})
        self.assertGreaterEqual(large, small)


class TestDeadlineExplanation(unittest.TestCase):
    def test_budget_is_named_when_it_cannot_hold_the_deadline(self):
        windows = [win("S1", "A", 0, 96), win("S2", "B", 0, 96)]
        streams = [{"name": "aocs", "rate_bps": 1500.0, "priority": 5, "deadline_hours": 6.0}]
        end = T0 + timedelta(hours=96)
        out = explain_unmet_deadlines(streams, windows, T0, end, schedule=[], delivery={"all_deadlines_met": False},
                                      prep_s=PREP, teardown_s=TEAR, min_tx_s=MINTX, daily_cap_s=3 * 3600,
                                      gross_bps=256000, overhead=0.2,
                                      size_rate_result={"status": "INFEASIBLE_WITH_GIVEN_GRANTS"})
        names = {f["constraint"] for f in out["findings"]}
        self.assertIn("DAILY_BUDGET", names)
        self.assertIn("CONTACT_TIME_NOT_RATE", names)
        self.assertIn("NOT_GEOMETRY_LIMITED", names)
        budget = next(f for f in out["findings"] if f["constraint"] == "DAILY_BUDGET")
        self.assertGreater(budget["required_hours"], budget["available_hours"])

    def test_met_deadlines_need_no_explanation(self):
        out = explain_unmet_deadlines(LOW, [win("S1", "A", 0, 5)], T0, T0 + timedelta(hours=5), schedule=[],
                                      delivery={"all_deadlines_met": True}, prep_s=PREP, teardown_s=TEAR,
                                      min_tx_s=MINTX, daily_cap_s=3 * 3600, gross_bps=256000, overhead=0.2)
        self.assertTrue(out["all_deadlines_met"])


if __name__ == "__main__":
    unittest.main()
