"""Smoke and invariant tests for preliminary adaptive storage planner."""
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from ttc.adaptive_storage import plan, shift_contacts, events_at

class AdaptiveStorageTests(unittest.TestCase):
    def test_shift_preserves_duration(self):
        a=datetime(2020,1,1,tzinfo=timezone.utc)
        b=datetime(2020,1,1,1,tzinfo=timezone.utc)
        c=[{"start":a,"end":b,"satellite":"SELENA_11","station":"Madrid"}]
        target=datetime(2030,7,14,tzinfo=timezone.utc)
        result=shift_contacts(c,target)
        self.assertEqual(result[0]["start"],target)
        self.assertEqual(result[0]["end"]-result[0]["start"],b-a)

    def test_event_scoping(self):
        a=datetime(2030,7,14,tzinfo=timezone.utc)
        e={"start":a,"end":a.replace(hour=1),"satellites":{"SELENA_11"}}
        self.assertEqual(len(events_at(a,[e],"SELENA_11")),1)
        self.assertEqual(len(events_at(a,[e],"SELENA_12")),0)

    def test_outputs_and_memory_accounting(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=plan(output_dir=tmp)
            self.assertEqual(len(r["satellites"]),8)
            self.assertTrue(Path(tmp,"adaptive_storage_history.csv").exists())
            self.assertTrue(Path(tmp,"adaptive_contact_schedule.csv").exists())
            for sat,v in r["satellites"].items():
                # Zero initial fill in example scenario: generation = downlink + remaining.
                self.assertAlmostEqual(v["generated_mbit"],v["downlinked_mbit"]+v["remaining_mbit"],delta=0.002)
                self.assertGreaterEqual(v["peak_memory_mbit"],v["remaining_mbit"])
            with open(Path(tmp,"adaptive_contact_schedule.csv"),newline="",encoding="utf-8") as f:
                import csv
                contacts=list(csv.DictReader(f))
            self.assertEqual(len(contacts),r["contacts"])
            for c in contacts:
                self.assertGreaterEqual(float(c["downloaded_mbit"]),0)

if __name__=="__main__":
    unittest.main()
