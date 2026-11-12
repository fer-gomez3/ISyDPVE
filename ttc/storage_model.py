"""Event-driven data storage model; unknown transmitter rates are never assumed."""
def simulate(assignments,start,end,generation_bps,downlink_bps=None,overhead=0.0):
    if generation_bps<0 or (downlink_bps is not None and downlink_bps<0):raise ValueError("Invalid bit rate")
    if not 0<=overhead<1 or end<=start:raise ValueError("Invalid time or overhead")
    events=sorted({start,end}|{max(start,min(end,x[t])) for x in assignments for t in ("start","end")})
    stored=peak=sent_total=0.0
    for a,b in zip(events,events[1:]):
        sec=(b-a).total_seconds()
        produced=generation_bps*sec
        peak=max(peak,stored+produced) # conservative segment-level bound
        active=any(x["start"]<=a and x["end"]>=b for x in assignments)
        sent=min(stored+produced,downlink_bps*(1-overhead)*sec) if active and downlink_bps is not None else 0.0
        stored+=produced-sent;sent_total+=sent
    return dict(generated_mbit=generation_bps*(end-start).total_seconds()/1e6,
                transmitted_mbit=sent_total/1e6,final_buffer_mbit=stored/1e6,
                conservative_peak_buffer_mbit=peak/1e6)
