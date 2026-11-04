from datetime import datetime,timezone,timedelta
from ttc.contact_analysis import candidate_schedule,summarize
from ttc.storage_model import simulate

def test_station_conflicts():
    t=datetime(2020,1,1,tzinfo=timezone.utc)
    c=[dict(id=str(i),station="Madrid",satellite="S"+str(i),start=t,end=t+timedelta(hours=1),seconds=3600) for i in range(3)]
    s=candidate_schedule(c)
    assert sum(x["seconds"] for x in s)<=3600
    assert summarize(c,s)["geometric_windows"]==3

def test_one_day_storage():
    t=datetime(2020,1,1,tzinfo=timezone.utc)
    assert abs(simulate([],t,t+timedelta(days=1),132)["final_buffer_mbit"]-11.4048)<1e-8

def test_transmission_reduces_storage():
    t=datetime(2020,1,1,tzinfo=timezone.utc)
    a=[dict(start=t+timedelta(hours=12),end=t+timedelta(hours=13))]
    r=simulate(a,t,t+timedelta(days=1),132,1000)
    assert r["transmitted_mbit"]>0
