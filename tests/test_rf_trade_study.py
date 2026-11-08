import unittest
from ttc.rf_trade_study import trade

class RFTradeTests(unittest.TestCase):
    def setUp(self):
        self.cfg={"frequency_hz":8.4e9,"distance_km":405000,
            "tx_diameters_m":[0.15,0.3,0.45],"tx_efficiency":0.55,
            "rx_gt_db_per_k":45,"required_ebn0_db":6,"losses_db":4,
            "margin_db":3,"pa_efficiency":0.35,"electronics_w":8}

    def test_larger_antenna_requires_less_rf_power(self):
        r=trade(self.cfg,256000,contact_hours=2)
        self.assertEqual(len(r["cases"]),3)
        self.assertGreater(r["cases"][0]["required_rf_w"],r["cases"][1]["required_rf_w"])
        self.assertGreater(r["cases"][1]["required_rf_w"],r["cases"][2]["required_rf_w"])
        self.assertAlmostEqual(r["cases"][0]["contact_energy_wh"],r["cases"][0]["tx_dc_w"]*2)

    def test_missing_inputs_are_reported(self):
        cfg=dict(self.cfg,rx_gt_db_per_k=None)
        self.assertEqual(trade(cfg,256000)["status"],"MISSING_RF_INPUTS")

    def test_invalid_rate_rejected(self):
        with self.assertRaises(ValueError):trade(self.cfg,0)

if __name__=="__main__":unittest.main()
