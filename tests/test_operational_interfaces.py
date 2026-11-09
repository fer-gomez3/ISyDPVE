"""Integration checks for DSN operations, deadline and EPS/TCS interfaces."""
import tempfile
import unittest
from datetime import datetime,timedelta,timezone
from ttc.operational_interfaces import policy_seconds,usable_contacts,electrical_thermal
from ttc.dsn_pipeline import run

class TestOperationalInterfaces(unittest.TestCase):
    def setUp(self):
        self.a=datetime(2020,1,1,tzinfo=timezone.utc)
        self.b=self.a+timedelta(hours=2)

    def test_policy_includes_acquisition_and_teardown(self):
        p=policy_seconds("standard_ttc")
        self.assertEqual(p["preparation_seconds"],55*60)
        self.assertEqual(p["teardown_seconds"],15*60)

    def test_usable_contact_excludes_both_overheads(self):
        c={"satellite":"S1","station":"Madrid","start":self.a,"end":self.b}
        useful=usable_contacts([c],55*60,15*60)
        self.assertEqual(len(useful),1)
        self.assertEqual(useful[0]["seconds"],50*60)

    def test_unknown_hardware_not_assumed_zero(self):
        x=electrical_thermal([],self.a,self.b,{"standby_w":None},None)
        self.assertIsNone(x["energy_wh_horizon"])
        self.assertIsNone(x["tx_heat_w"])

    def test_energy_and_heat_conservation(self):
        c=[{"start":self.a,"end":self.a+timedelta(hours=1)}]
        x=electrical_thermal(c,self.a,self.b,{"standby_w":10,"tx_dc_w":20,
            "gimbal_tracking_w":5,"memory_interface_w":2},rf_power_w=4)
        self.assertAlmostEqual(x["energy_wh_horizon"],47)
        self.assertAlmostEqual(x["tx_heat_w"],33)
        self.assertAlmostEqual(x["tx_heat_wh_horizon"],33)

    def test_integrated_deadline_results_and_graphs(self):
        with tempfile.TemporaryDirectory() as d:
            result=run(output_dir=d,make_plots=False)
            self.assertIn("deadline_results",result)
            self.assertIn("operational_policy",result)
            self.assertIn("electrical_thermal",next(iter(result["satellites"].values())))
