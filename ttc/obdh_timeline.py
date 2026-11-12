"""Time-resolved SELENA OBDH ledger for assigned DSN contacts.

All rates are per spacecraft. Unknown rates must be resolved by caller; this model
does not claim to simulate missing telemetry or actual DSN bookings.
"""
from datetime import timedelta
import math

def timeline(assignments, start, end, generation_bps, downlink_bps, overhead=0.2,
             step_seconds=60, initial_bits=0):
    if end <= start or not 0 <= overhead < 1 or step_seconds <= 0:
        raise ValueError("Invalid timeline configuration")
    if any(not math.isfinite(v) or v < 0 for v in (generation_bps,downlink_bps,initial_bits)):
        raise ValueError("Invalid bit rate or buffer")
    contacts=sorted(assignments,key=lambda x:x["start"])
    for c in contacts:
        if c["end"]<=c["start"] or c["start"]<start or c["end"]>end:
            raise ValueError("Contact outside simulation horizon")
    for a,b in zip(contacts,contacts[1:]):
        if a["end"]>b["start"]:
            raise ValueError("Overlapping spacecraft contacts; resolve before simulation")
    times={start,end}
    for c in contacts:
        times.update((c["start"],c["end"]))
    cursor=start
    while cursor<end:
        cursor=min(end,cursor+timedelta(seconds=step_seconds))
        times.add(cursor)
    times=sorted(times)
    stored=float(initial_bits); generated=sent=0.0; peak=stored
    rows=[dict(time_utc=start.isoformat(),buffer_mbit=stored/1e6,
               generated_cumulative_mbit=0.,downlinked_cumulative_mbit=0.,
               downlinked_interval_mbit=0.,contact_active=False)]
    for a,b in zip(times,times[1:]):
        seconds=(b-a).total_seconds()
        produced=generation_bps*seconds
        active=any(c["start"]<=a and b<=c["end"] for c in contacts)
        capacity=downlink_bps*(1-overhead)*seconds if active else 0.
        # Continuous production and transmission within interval.
        transferred=min(stored+produced,capacity)
        stored+=produced-transferred
        generated+=produced;sent+=transferred
        peak=max(peak,stored)
        rows.append(dict(time_utc=b.isoformat(),buffer_mbit=stored/1e6,
            generated_cumulative_mbit=generated/1e6,
            downlinked_cumulative_mbit=sent/1e6,
            downlinked_interval_mbit=transferred/1e6,contact_active=active))
    assert abs(initial_bits+generated-sent-stored)<max(1e-5,generated*1e-10)
    return {"rows":rows,"generated_mbit":generated/1e6,
        "transmitted_mbit":sent/1e6,"final_buffer_mbit":stored/1e6,
        "peak_sampled_buffer_mbit":peak/1e6,
        "contact_count":len(contacts),"status":"SCENARIO_KNOWN_TELEMETRY_ONLY"}
