import unittest
from ttc.ground_delivery import simulate,size_rate

class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.streams=[{"name":"aocs","rate_bps":100,"priority":5,"deadline_hours":2}]
        self.windows=[{"satellite":"S1","station":"Madrid","start_utc":"2030-01-01T00:00:00Z","end_utc":"2030-01-01T06:00:00Z"}]
        self.grants=[{"satellite":"S1","station":"Madrid","start_utc":"2030-01-01T00:00:00Z","end_utc":"2030-01-01T06:00:00Z"}]

    def test_continuous_contact_feasible(self):
        r=simulate(self.streams,self.windows,self.grants,gross_bps=1000,setup_minutes=0,step_seconds=60)
        self.assertTrue(r["all_deadlines_met"])
        self.assertAlmostEqual(r["satellites"]["S1"]["produced_bits"],2160000)

    def test_no_useful_time_fails(self):
        r=simulate(self.streams,self.windows,self.grants,gross_bps=100000,setup_minutes=360)
        self.assertFalse(r["all_deadlines_met"])

    def test_rate_search(self):
        r=size_rate(self.streams,self.windows,self.grants,setup_minutes=0,step_seconds=60,max_bps=1000,tolerance_bps=1)
        self.assertEqual(r["status"],"PRELIMINARY_RATE_FEASIBLE")
        self.assertTrue(r["simulation"]["all_deadlines_met"])

    def test_impossible_contact_gap(self):
        g=[{"satellite":"S1","station":"Madrid","start_utc":"2030-01-01T04:00:00Z","end_utc":"2030-01-01T06:00:00Z"}]
        r=size_rate(self.streams,self.windows,g,setup_minutes=0,max_bps=1000000,step_seconds=60)
        self.assertEqual(r["status"],"INFEASIBLE_WITH_GIVEN_GRANTS")

    def test_station_overlap_rejected(self):
        g=self.grants+[dict(self.grants[0],satellite="S2")]
        w=self.windows+[dict(self.windows[0],satellite="S2")]
        with self.assertRaises(ValueError):
            simulate(self.streams,w,g,gross_bps=1000)

if __name__=="__main__":unittest.main()
