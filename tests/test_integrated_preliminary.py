import json
import tempfile
import unittest
from pathlib import Path
from ttc.integrated_preliminary import run

class IntegratedPreliminaryTests(unittest.TestCase):
    def test_end_to_end_report(self):
        with tempfile.TemporaryDirectory() as d:
            result=run(output_dir=d,step_seconds=300)
            self.assertEqual(result["status"],"PRELIMINARY_SYNTHETIC_GEOMETRY_NOT_FLIGHT_VALIDATED")
            self.assertTrue(Path(result["report"]).is_file())
            data=json.loads(Path(result["json"]).read_text(encoding="utf-8"))
            self.assertEqual(len(data["satellite_summary"]),8)
            self.assertEqual(len(data["delivery"]["satellites"]),8)
            self.assertIn("rf_budget",data)
            self.assertIn("required_rate",data)
            self.assertTrue((Path(d)/"integrated_contact_requests.csv").is_file())

if __name__=="__main__":unittest.main()
