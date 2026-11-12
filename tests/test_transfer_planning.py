from ttc.transfer_planning import stream_rate,stream_requirements

def test_event_rate():
    assert stream_rate(dict(mode="event",bytes_per_event=4500,event_interval_hours=1))==10

def test_policy():
    cfg=dict(policy=dict(priority_max_age_hours={str(i):float(i) for i in range(1,6)}),
             streams=[dict(name="x",priority=3,mode="continuous",rate_bps=100)])
    r=stream_requirements(cfg)[0]
    assert r["deadline_hours"]==3
    assert r["generated_mbit_per_day"]==8.64
