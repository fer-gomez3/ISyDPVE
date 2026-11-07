import unittest
from ttc.ground_protocol_planner import plan

class GroundProtocolPlannerTests(unittest.TestCase):
    def setUp(self):
        self.streams=[{"name":"aocs","rate_bps":100,"priority":5,"deadline_hours":6}]
        self.windows=[{"satellite":"S1","station":"Madrid","start_utc":"2030-01-01T00:00:00Z","end_utc":"2030-01-01T12:00:00Z"}]
        self.grants=[{"satellite":"S1","station":"Madrid","start_utc":"2030-01-01T02:00:00Z","end_utc":"2030-01-01T04:00:00Z"}]

    def test_granted_time_and_rate(self):
        r=plan(self.streams,self.windows,self.grants,utilization=0.5,overhead=0.2,setup_minutes=15,design_margin=0.2)
        c=r["contacts"][0]
        self.assertEqual(c["usable_seconds"],2700)
        self.assertAlmostEqual(c["nominal_payload_bits"],1440000)
        self.assertAlmostEqual(c["required_gross_bps"],1440000/2700/0.8)
        self.assertAlmostEqual(r["maximum_design_gross_bps"],c["required_gross_bps"]*1.2)

    def test_grant_outside_visibility_rejected(self):
        bad=[dict(self.grants[0],end_utc="2030-01-01T13:00:00Z")]
        with self.assertRaises(ValueError):
            plan(self.streams,self.windows,bad)

    def test_zero_useful_time(self):
        r=plan(self.streams,self.windows,self.grants,utilization=0.1,setup_minutes=15)
        self.assertEqual(r["contacts"][0]["status"],"NO_USEFUL_TIME")

    def test_long_gap_flagged(self):
        r=plan(self.streams,self.windows,self.grants)
        self.assertTrue(any(x["reason"]=="END_OF_HORIZON_UNSERVED" for x in r["deadline_risks"]))

if __name__=="__main__":
    unittest.main()
