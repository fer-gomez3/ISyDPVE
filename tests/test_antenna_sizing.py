"""ttc.antenna_sizing: continuous dish sizing. Inputs are illustrative test values."""
import unittest
from ttc.antenna_sizing import minimum_diameter

RF = dict(frequency_hz=8.4e9, distance_km=405000, tx_efficiency=.55,
          pointing_error_deg=.15, rx_gt_db_per_k=45, required_ebn0_db=6,
          losses_db=4, margin_db=3, pa_efficiency=.35, electronics_w=8)


class TestAntennaSizing(unittest.TestCase):
    def test_sized_diameter_meets_power_cap_and_is_minimal(self):
        r = minimum_diameter(RF, 256000, max_tx_rf_w=0.2)
        self.assertEqual(r["status"], "SIZED_WITHIN_BOUNDS")
        d = r["diameter_m"]
        self.assertLessEqual(r["link"]["required_rf_w"], 0.2)
        smaller = minimum_diameter(RF, 256000, 0.2, minimum_m=d - 0.001, maximum_m=d - 0.0005)
        self.assertEqual(smaller["status"], "NO_FEASIBLE_DIAMETER_WITHIN_BOUNDS")

    def test_tighter_power_cap_needs_larger_dish(self):
        loose = minimum_diameter(RF, 256000, 0.5)["diameter_m"]
        tight = minimum_diameter(RF, 256000, 0.1)["diameter_m"]
        self.assertGreater(tight, loose)

    def test_higher_rate_needs_larger_dish(self):
        low = minimum_diameter(RF, 64000, 0.2)["diameter_m"]
        high = minimum_diameter(RF, 256000, 0.2)["diameter_m"]
        self.assertGreater(high, low)

    def test_no_power_cap_returns_no_diameter(self):
        r = minimum_diameter(RF, 256000, None)
        self.assertEqual(r["status"], "MISSING_RF_POWER_CAP")
        self.assertIsNone(r["diameter_m"])

    def test_incomplete_link_inputs_do_not_invent_a_diameter(self):
        r = minimum_diameter({"frequency_hz": 8.4e9, "tx_efficiency": .55}, 256000, 0.2)
        self.assertEqual(r["status"], "INCOMPLETE_LINK_INPUTS")
        self.assertIsNone(r["diameter_m"])

    def test_infeasible_within_bounds(self):
        r = minimum_diameter(RF, 256000, 1e-9)
        self.assertEqual(r["status"], "NO_FEASIBLE_DIAMETER_WITHIN_BOUNDS")
        self.assertIsNone(r["diameter_m"])

    def test_invalid_bounds_rejected(self):
        with self.assertRaises(ValueError):
            minimum_diameter(RF, 256000, -1)
        with self.assertRaises(ValueError):
            minimum_diameter(RF, 256000, 0.2, minimum_m=2, maximum_m=1)


if __name__ == "__main__":
    unittest.main()
