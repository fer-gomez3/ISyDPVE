"""Unit tests for communications-only electrical and aperture model."""
import unittest
from ttc.communications_budget import power_modes, antenna_options, run

class CommunicationsBudgetTests(unittest.TestCase):
    def test_unknown_not_zero(self):
        r = power_modes({"standby_w": 2}, {"lunar_rx": 1})
        self.assertIsNone(r["energy_wh_per_day"])
        self.assertIn("lunar_receiver_w", r["modes"]["lunar_rx"]["missing_inputs"])

    def test_shared_memory_not_double_counted(self):
        p = dict(standby_w=1, lunar_receiver_w=2, lunar_processing_w=3,
                 memory_interface_w=4, tx_dc_w=5, gimbal_tracking_w=6,
                 gimbal_slew_w=7)
        r = power_modes(p, {"simultaneous": 2, "standby": 22})
        self.assertEqual(r["modes"]["simultaneous"]["power_w"], 21)
        self.assertEqual(r["energy_wh_per_day"], 64)
        self.assertAlmostEqual(r["average_w_over_24h"], 64/24)
        self.assertEqual(r["peak_w_in_scheduled_modes"], 21)

    def test_invalid_durations(self):
        with self.assertRaises(ValueError):
            power_modes({}, {"standby": 25})
        with self.assertRaises(ValueError):
            power_modes({}, {"standby": -1})

    def test_diameter_monotonic_rf_power(self):
        rf = dict(frequency_hz=8.4e9, distance_km=405000, tx_efficiency=.55,
                  pointing_error_deg=.15, rx_gt_db_per_k=45, required_ebn0_db=6,
                  losses_db=4, margin_db=3, pa_efficiency=.35, electronics_w=8)
        result = antenna_options(rf, 256000, [.15, .30, .45], .2)
        cases = result["cases"]
        self.assertGreater(cases[0]["required_rf_w"], cases[1]["required_rf_w"])
        self.assertGreater(cases[1]["required_rf_w"], cases[2]["required_rf_w"])
        self.assertAlmostEqual(cases[1]["tx_dc_w"], 8.338054, places=3)
        self.assertEqual(result["smallest_tested_feasible_diameter_cm"], 30)

    def test_missing_link_inputs_no_fake_diameter(self):
        r = antenna_options({"frequency_hz": 8.4e9, "tx_efficiency": .55}, 256000, [.3], .2)
        self.assertIsNone(r["smallest_tested_feasible_diameter_cm"])
        self.assertIsNone(r["cases"][0]["required_rf_w"])

    def test_current_configuration_explicitly_incomplete(self):
        r = run()
        self.assertIsNone(r["communications_power"]["energy_wh_per_day"])
        self.assertEqual(r["selected_diameter_cm"], 30)
        self.assertIsNone(r["antenna"]["smallest_tested_feasible_diameter_cm"])

if __name__ == "__main__":
    unittest.main()
