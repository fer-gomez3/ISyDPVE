"""Telemetry profile regression tests: never label assumptions as confirmed."""
import tempfile
import unittest
from pathlib import Path
from ttc.dsn_pipeline import run

class TestTelemetryProfiles(unittest.TestCase):
    def test_confirmed_profile_keeps_known_subtotal(self):
        with tempfile.TemporaryDirectory() as d:
            r=run(output_dir=d)
            self.assertEqual(r["telemetry_profile"],"confirmed")
            self.assertAlmostEqual(r["known_generation_bps"],132.0)
            self.assertAlmostEqual(r["modeled_generation_bps"],132.0)
            self.assertIsNone(r["scenario_streams"])

    def test_assumed_profile_has_provenance_warning(self):
        with tempfile.TemporaryDirectory() as d:
            r=run(output_dir=d,telemetry_profile="scenario")
            self.assertEqual(r["telemetry_profile"],"scenario")
            self.assertEqual(r["scenario_warning"],"ASSUMED_RATES_NOT_CONFIRMED")
            self.assertEqual(len(r["scenario_streams"]),7)
            self.assertGreater(r["modeled_generation_bps"],r["known_generation_bps"])

    def test_invalid_profile_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                run(output_dir=d,telemetry_profile="unverified")
