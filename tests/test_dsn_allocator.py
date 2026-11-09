from datetime import datetime,timedelta,timezone
import unittest
from ttc.dsn_allocator import allocate,verify_contacts

class TestDSNAllocator(unittest.TestCase):
    def setUp(self):
        self.t=datetime(2020,1,1,tzinfo=timezone.utc)
    def contact(self,sat,station,offset,duration):
        a=self.t+timedelta(seconds=offset);b=a+timedelta(seconds=duration)
        return dict(satellite=sat,station=station,start=a,end=b,seconds=duration)
    def test_station_and_spacecraft_never_double_booked(self):
        rows=[self.contact("S1","Madrid",0,600),
              self.contact("S2","Madrid",0,600),
              self.contact("S1","Goldstone",0,600)]
        out=allocate(rows)
        # One antenna per station and one link per spacecraft: S1 takes
        # Goldstone (earliest-end tie-break), so Madrid is free for S2 and the
        # S1/Madrid candidate is dropped. Two contacts, never overlapping.
        self.assertEqual({(c["satellite"],c["station"]) for c in out},
                         {("S1","Goldstone"),("S2","Madrid")})
        for key in ("station","satellite"):
            for name in {c[key] for c in out}:
                rows_k=sorted((c for c in out if c[key]==name),key=lambda c:c["start"])
                for a,b in zip(rows_k,rows_k[1:]):
                    self.assertLessEqual(a["end"],b["start"])
    def test_availability_clips_contact(self):
        rows=[self.contact("S1","Madrid",0,1200)]
        a=self.t+timedelta(seconds=300)
        b=self.t+timedelta(seconds=900)
        out=allocate(rows,{"Madrid":[(a,b)]},minimum_seconds=300,setup_seconds=60)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["usable_seconds"],540)
        self.assertEqual(out[0]["start"],a)
    def test_too_short_window_rejected(self):
        self.assertEqual(allocate([self.contact("S1","Madrid",0,200)]),[])
    def test_gap_detected(self):
        out=verify_contacts([],["S1"],self.t,self.t+timedelta(hours=25))
        self.assertFalse(out["S1"]["meets_max_gap"])
