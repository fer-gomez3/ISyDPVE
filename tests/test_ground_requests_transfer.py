import unittest
from ttc.ground_requests import propose
from ttc.transfer_protocol import TransferSession

class GroundRequestTests(unittest.TestCase):
    def setUp(self):
        self.streams=[{"name":"aocs","rate_bps":100,"deadline_hours":2,"priority":5}]
        self.windows=[{"satellite":"S1","station":"Madrid","start_utc":"2030-01-01T00:00:00Z","end_utc":"2030-01-01T06:00:00Z"}]

    def test_requests_and_candidate(self):
        r=propose(self.streams,self.windows,gross_bps=1000,setup_minutes=0,utilization=1)
        self.assertEqual(len(r["requests"]),3)
        self.assertEqual(r["requests"][0]["nominal_payload_bits"],720000)
        self.assertTrue(r["requests"][0]["candidate_windows"])

    def test_no_window_long_enough(self):
        r=propose(self.streams,self.windows,gross_bps=10,setup_minutes=0,utilization=1)
        self.assertEqual(r["requests"][0]["status"],"NO_SINGLE_WINDOW_LONG_ENOUGH")

    def test_invalid_rate(self):
        with self.assertRaises(ValueError):
            propose(self.streams,self.windows,gross_bps=0)

class ProtocolTests(unittest.TestCase):
    def test_ack_retry_release(self):
        s=TransferSession("S1")
        s.enqueue("aocs",5,"2030-01-01T02:00:00Z",b"first","a")
        s.enqueue("eps",3,"2030-01-01T04:00:00Z",b"second","b")
        self.assertEqual(s.transmit(5),["a"])
        self.assertEqual(s.transmit(11),["a","b"])
        s.acknowledge(["a"])
        self.assertEqual(s.manifest()[0]["status"],"CONFIRMED")
        self.assertEqual(s.release_confirmed(),1)
        self.assertEqual(s.stored_bytes,6)
        self.assertEqual(s.transmit(6),["b"])

    def test_unsent_ack_rejected(self):
        s=TransferSession("S1")
        s.enqueue("aocs",5,"2030-01-01T02:00:00Z",b"first","a")
        with self.assertRaises(ValueError):
            s.acknowledge(["a"])

if __name__=="__main__":unittest.main()
