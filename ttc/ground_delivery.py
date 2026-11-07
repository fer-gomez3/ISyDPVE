"""Deadline-aware SELENA ground contact demand and delivery simulator.

A deterministic, constant-generation, fluid-bit model. Grants are externally
supplied and never construed as DSN bookings. No packet-level ACKs are simulated.
"""
from datetime import timedelta
from .ground_protocol_planner import utc

def _validate(streams, visibility, grants):
    if not streams or not visibility: raise ValueError("Streams and visibility required")
    seen=set()
    for s in streams:
        if s["name"] in seen or float(s["rate_bps"])<0 or float(s["deadline_hours"])<=0 or int(s["priority"]) not in range(1,6):
            raise ValueError("Invalid stream")
        seen.add(s["name"])
    windows={}
    for w in visibility:
        a,b=utc(w["start_utc"]),utc(w["end_utc"])
        if b<=a:raise ValueError("Invalid visibility")
        windows.setdefault((w["satellite"],w["station"]),[]).append((a,b))
    by_station={};by_sat={}
    for g in grants:
        a,b=utc(g["start_utc"]),utc(g["end_utc"])
        if b<=a or not any(x<=a and b<=y for x,y in windows.get((g["satellite"],g["station"]),[])):
            raise ValueError("Grant outside visibility")
        by_station.setdefault(g["station"],[]).append((a,b))
        by_sat.setdefault(g["satellite"],[]).append((a,b))
    for collection in (by_station,by_sat):
        for key,intervals in collection.items():
            intervals.sort()
            if any(intervals[i][0]<intervals[i-1][1] for i in range(1,len(intervals))):
                raise ValueError("Overlapping granted antenna or spacecraft: "+key)
    return windows

def simulate(streams,visibility,grants,*,gross_bps,utilization=1.0,
             overhead=0.2,setup_minutes=15,step_seconds=30,
             start_utc=None,end_utc=None):
    """Time-step FIFO model with per-stream max-age checks.

    Deadline violations are evaluated using oldest generated undelivered bit.
    Fluid-bit transmission and perfect delivery are assumed. A confirmed
    delivery requires a separate ACK implementation.
    """
    windows=_validate(streams,visibility,grants)
    if gross_bps<0 or not 0<utilization<=1 or not 0<=overhead<1 or setup_minutes<0 or step_seconds<=0:
        raise ValueError("Invalid physical parameters")
    start=utc(start_utc) if start_utc else min(a for vals in windows.values() for a,b in vals)
    end=utc(end_utc) if end_utc else max(b for vals in windows.values() for a,b in vals)
    if end<=start:raise ValueError("Invalid horizon")
    sats=sorted({k[0] for k in windows})
    schedule={}
    for g in grants:
        a,b=utc(g["start_utc"]),utc(g["end_utc"])
        # Utilization is a fraction of granted duration, not of geometric visibility.
        finish=a+timedelta(seconds=(b-a).total_seconds()*utilization)
        tx_start=a+timedelta(minutes=setup_minutes)
        schedule.setdefault(g["satellite"],[]).append((tx_start,finish,g["station"]))
    for sat in schedule:schedule[sat].sort()
    result={}
    for sat in sats:
        backlog={s["name"]:0.0 for s in streams}
        produced={s["name"]:0.0 for s in streams}
        sent={s["name"]:0.0 for s in streams}
        oldest={s["name"]:None for s in streams}
        peak=0.0;violations=set();deadline_events=[]
        windows_sat=schedule.get(sat,[])
        t=start
        while t<end:
            dt=min(step_seconds,(end-t).total_seconds())
            next_t=t+timedelta(seconds=dt)
            # Generate uniformly; timestamp midpoint approximates generation time.
            for s in streams:
                name=s["name"];rate=float(s["rate_bps"])
                if rate>0:
                    if backlog[name]<=1e-8:oldest[name]=t
                    amount=rate*dt
                    backlog[name]+=amount;produced[name]+=amount
            # Transmission interval overlap; never transmit outside a grant.
            usable=sum(max(0,(min(next_t,b)-max(t,a)).total_seconds())
                       for a,b,station in windows_sat if b>a)
            capacity=gross_bps*(1-overhead)*usable
            # Earliest deadline first, priority as tie breaker, FIFO within stream.
            order=sorted(streams,key=lambda s:(oldest[s["name"]]+timedelta(hours=float(s["deadline_hours"]))
                         if oldest[s["name"]] is not None else end+timedelta(days=1),
                         -int(s["priority"]),s["name"]))
            for s in order:
                name=s["name"]
                take=min(capacity,backlog[name])
                if take<=0:continue
                before=backlog[name];backlog[name]-=take;sent[name]+=take;capacity-=take
                if backlog[name]<1e-8:
                    backlog[name]=0.0;oldest[name]=None
                else:
                    # FIFO with constant generation; consumed bits advance oldest age.
                    oldest[name]=oldest[name]+timedelta(seconds=take/float(s["rate_bps"]))
            peak=max(peak,sum(backlog.values()))
            for s in streams:
                name=s["name"]
                if oldest[name] is not None and next_t-oldest[name]>timedelta(hours=float(s["deadline_hours"])):
                    if name not in violations:
                        deadline_events.append({"subsystem":name,"first_violation_utc":next_t.isoformat()})
                    violations.add(name)
            t=next_t
        result[sat]={"produced_bits":sum(produced.values()),"delivered_bits_assuming_perfect_link":sum(sent.values()),
                     "remaining_bits":sum(backlog.values()),"peak_backlog_bits":peak,
                     "deadline_violations":sorted(violations),"deadline_events":deadline_events,
                     "by_stream":{s["name"]:{"produced_bits":produced[s["name"]],
                                           "delivered_bits":sent[s["name"]],
                                           "remaining_bits":backlog[s["name"]]} for s in streams}}
    return {"status":"SIMULATED_UNCONFIRMED_DELIVERY","gross_bps":gross_bps,
            "effective_bps":gross_bps*(1-overhead),"satellites":result,
            "all_deadlines_met":all(not s["deadline_violations"] for s in result.values()),
            "limitations":"Perfect reception, constant generation, fluid bits, no ACK/ARQ or RF link losses; deadline ages discretized to step_seconds."}

def size_rate(streams,visibility,grants,*,min_bps=1,max_bps=100000000,
              tolerance_bps=1,**kwargs):
    """Binary-search minimum gross rate for modeled per-stream deadlines.

    If even infinite rate cannot compensate for unavailable contacts, reports
    infeasible rather than inventing an antenna or power.
    """
    if min_bps<=0 or max_bps<min_bps or tolerance_bps<=0:raise ValueError("Invalid search bounds")
    high=simulate(streams,visibility,grants,gross_bps=max_bps,**kwargs)
    if not high["all_deadlines_met"]:
        return {"status":"INFEASIBLE_WITH_GIVEN_GRANTS","required_gross_bps":None,"simulation":high}
    low=0.0;upper=float(max_bps)
    while upper-low>tolerance_bps:
        mid=(low+upper)/2
        r=simulate(streams,visibility,grants,gross_bps=mid,**kwargs)
        if r["all_deadlines_met"]:upper=mid
        else:low=mid
    return {"status":"PRELIMINARY_RATE_FEASIBLE","required_gross_bps":upper,
            "simulation":simulate(streams,visibility,grants,gross_bps=upper,**kwargs)}
