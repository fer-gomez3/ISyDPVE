import tempfile
import unittest
from pathlib import Path
from ttc.packet_transfer import PacketTransfer

class PacketTransferTests(unittest.TestCase):
    def test_resume_selective_ack_and_release(self):
        p=PacketTransfer("SELENA_11",fragment_bytes=4)
        p.enqueue("A",b"abcdefghij",priority=5,deadline_utc="2030-01-01T06:00:00Z")
        first=p.transmit(8)
        self.assertEqual([(x["file_id"],x["fragment_index"]) for x in first],[("A",0),("A",1)])
        p.acknowledge([("A",0)])
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"state.json"
            p.checkpoint(path)
            restored=PacketTransfer.restore(path)
            next_packets=restored.transmit(6)
            self.assertEqual([x["fragment_index"] for x in next_packets],[1,2])
            restored.acknowledge([("A",1),("A",2)])
            self.assertEqual(restored.complete_files(),["A"])
            self.assertEqual(restored.release_confirmed(),["A"])
            self.assertEqual(restored.files,{})

    def test_unsent_ack_rejected(self):
        p=PacketTransfer("S1",fragment_bytes=2)
        p.enqueue("A",b"abcd")
        with self.assertRaises(ValueError):p.acknowledge([("A",1)])

    def test_corrupt_checkpoint_rejected(self):
        p=PacketTransfer("S1",fragment_bytes=2)
        p.enqueue("A",b"abcd")
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"state.json"
            p.checkpoint(path)
            content=path.read_text().replace("YWI=","eHg=")
            path.write_text(content)
            with self.assertRaises(ValueError):PacketTransfer.restore(path)

if __name__=="__main__":unittest.main()
