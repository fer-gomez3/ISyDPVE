from datetime import datetime,timedelta,timezone
import unittest
from ttc.obdh_timeline import timeline

class TestOBDHTimeline(unittest.TestCase):
    def setUp(self):
        self.start=datetime(2020,1,1,tzinfo=timezone.utc)
        self.end=self.start+timedelta(hours=2)

    def test_no_contact_accumulates(self):
        result=timeline([],self.start,self.end,100,1000,step_seconds=300)
        self.assertAlmostEqual(result["final_buffer_mbit"],0.72)
        self.assertEqual(result["transmitted_mbit"],0)

    def test_download_only_during_contact(self):
        contacts=[{"start":self.start+timedelta(hours=1),"end":self.end}]
        result=timeline(contacts,self.start,self.end,100,1000,overhead=0,step_seconds=60)
        self.assertAlmostEqual(result["generated_mbit"],0.72)
        self.assertAlmostEqual(result["transmitted_mbit"],0.72)
        self.assertAlmostEqual(result["final_buffer_mbit"],0)
        for row in result["rows"]:
            if not row["contact_active"]:
                self.assertEqual(row["downlinked_interval_mbit"],0)

    def test_overlapping_contacts_rejected(self):
        contacts=[{"start":self.start,"end":self.end},
                  {"start":self.start+timedelta(minutes=1),"end":self.end}]
        with self.assertRaises(ValueError):
            timeline(contacts,self.start,self.end,100,1000)
