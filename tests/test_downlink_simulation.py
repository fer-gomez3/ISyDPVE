"""Smoke tests for contact allocation and downlink accounting."""
from datetime import datetime,timezone,timedelta
from ttc.downlink_simulation import run

def test_download_never_exceeds_capacity():
    start=datetime(2020,1,1,tzinfo=timezone.utc)
    contacts=[dict(id="c1",station="Madrid",satellite="SELENA_11",
                   start=start,end=start+timedelta(hours=2),seconds=7200)]
    cfg={"policy":{"protocol_overhead_fraction":0.2,"net_downlink_bps":256000,
        "priority_max_age_hours":{"3":24}},
        "streams":[{"name":"payload_housekeeping","mode":"continuous",
                    "rate_bps":100,"priority":3,"max_age_hours":24}]}
    policy={"default_fraction":0.4,"setup_minutes":5,"min_contact_minutes":15}
    r=run(cfg,contacts,policy)
    assert r["status"]=="HYPOTHETICAL_SCENARIO"
    for c in r["contacts"]:
        assert c["downloaded_mbit"]<=c["capacity_mbit"]+1e-9
    s=r["satellites"]["SELENA_11"]
    assert abs(s["generated_mbit"]-s["downloaded_mbit"]-s["remaining_mbit"])<1e-6
