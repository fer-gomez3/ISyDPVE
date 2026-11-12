"""Basic sensitivity scenario integrity checks."""
import tempfile
import unittest
from pathlib import Path
from ttc.dsn_sensitivity import run

class TestDsnSensitivity(unittest.TestCase):
    def test_multiple_budget_scenarios(self):
        with tempfile.TemporaryDirectory() as tmp:
            result=run(hours=(1,3),output_dir=tmp)
            self.assertEqual([r["daily_budget_h"] for r in result["cases"]],[1.,3.])
            self.assertTrue((Path(tmp)/"sensitivity.csv").exists())
            for row in result["cases"]:
                self.assertLessEqual(row["reserved_h"],row["daily_budget_h"]*5+0.01)
                self.assertLessEqual(row["useful_tx_h"],row["reserved_h"])
                self.assertLessEqual(row["satellites_with_deadline_violations"],8)
            self.assertIn("NOT_DSN_BOOKED",result["status"])

    def test_invalid_hours_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run(hours=(0,),output_dir=tmp)
