import unittest
from ttc.mandatory_link_sizing import rf_trade

class MandatoryLinkSizingTests(unittest.TestCase):
    def test_missing_rf_parameters_are_explicit(self):
        result=rf_trade(100000,{"frequency_hz":None})
        self.assertEqual(result["status"],"TBD_RF_INPUTS")
        self.assertIn("receiver_noise_temperature_K",result["missing"])

    def test_power_diameter_trade(self):
        case=dict(frequency_hz=8.4e9,distance_m=384400000,
                  rx_diameter_m=34,rx_efficiency=0.6,tx_efficiency=0.6,
                  tx_line_efficiency=0.8,receiver_noise_temperature_K=100,
                  required_Eb_N0_dB=10,additional_losses_dB=3,
                  min_diameter_m=0.5,max_diameter_m=2.0,diameter_step_m=0.5,
                  min_power_w=1,max_power_w=100,power_step_w=1)
        result=rf_trade(100000,case)
        self.assertEqual(result["status"],"FEASIBLE_PRELIMINARY")
        self.assertGreaterEqual(result["minimum_diameter"]["eb_n0_margin_db"],-1e-7)

if __name__=="__main__":
    unittest.main()
