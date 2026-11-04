"""Priority-cyclic downlink and volume-proportional shared memory allocation.
A tier-k window serves k,k-1,...,1,5,...,k+1, stopping when time runs out.
"""
def tier_order(tier):
    tier=int(tier)
    if tier not in range(1,6): raise ValueError("Priority tier must be 1..5")
    return list(range(tier,0,-1))+list(range(5,tier,-1))

def ordered_streams(streams,tier):
    order=tier_order(tier)
    return sorted(streams,key=lambda s:(order.index(int(s["priority"])),float(s["deadline_hours"]),s["name"]))

def choose_due_tier(streams,last_served,now,default=5):
    """Select most overdue deadline tier; avoid permanent starvation of lower tiers."""
    due=[]
    for s in streams:
        p=int(s["priority"])
        last=last_served.get(p,now)
        elapsed=(now-last).total_seconds()/3600
        deadline=float(s["deadline_hours"])
        if elapsed>=deadline: due.append((elapsed/deadline,-p,p))
    return max(due)[2] if due else default

def volume_shares(volumes,capacity_mbit,reserve_fraction=0.15):
    """Proportional quotas for positive volumes, keeping unassigned safety reserve."""
    if capacity_mbit<=0 or not 0<=reserve_fraction<1: raise ValueError("Invalid capacity/reserve")
    if any(v is None or v<0 for v in volumes.values()): raise ValueError("Unknown or negative volume")
    total=sum(volumes.values())
    if total<=0: raise ValueError("No positive volumes")
    usable=capacity_mbit*(1-reserve_fraction)
    return {name:{"volume_mbit":v,"share_fraction":v/total,
                   "quota_mbit":usable*v/total} for name,v in volumes.items()}
