"""Unified, deadline- and equity-aware preliminary DSN contact scheduler.

One scheduling criterion for ``dsn_pipeline`` and ``integrated_preliminary``.

Constraints that are always respected
    * a contact lies inside one geometric visibility window (satellite, station);
    * one antenna per station and one link per satellite, no overlaps;
    * every contact is a full RESERVATION = preparation (setup + acquisition)
      + transmission + teardown; only the transmission part moves data;
    * the shared DSN budget (hours per UTC day, all satellites together) counts
      the full reservation, as in ``adaptive_storage``;
    * a contact carries at least the minimum useful transmission time.

Policy (nothing here forces a positive result)
    1. Coverage guard: if some set of minimum-length contacts exists that serves
       every satellite at least once, the schedule contains one. Those "anchors"
       are reserved up front and released as soon as the satellite is served by a
       regular contact. If no such set exists, the binding constraints are
       reported (geometry, availability, daily budget, station conflict).
    2. Critical deadlines first: a satellite is critical when a stream would
       exceed its maximum age before a minimal pass could finish. Critical
       satellites are ordered by the highest stream priority at risk, then by
       smallest slack.
    3. Equity: remaining worthwhile satellites are ordered by the usable
       transmission time already received (least first).

Visibility from the 2020 propagator run is NOT confirmed DSN availability and the
hours-per-day budget is a hypothetical planning value. The result is a
preliminary allocation, never a booking.
"""
import math
from datetime import datetime, timedelta, timezone

STATUS = "HYPOTHETICAL_ALLOCATION_NOT_DSN_BOOKING"


def _utc(d):
    if isinstance(d, str):
        d = datetime.fromisoformat(d.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("UTC offset required")
    return d.astimezone(timezone.utc)


def _midnight_after(t):
    return datetime.combine(t.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)


def _day_slices(a, b):
    cur = a
    while cur < b:
        nxt = min(b, _midnight_after(cur))
        yield cur.date().isoformat(), (nxt - cur).total_seconds()
        cur = nxt


class _Ledger:
    """Occupation of stations, satellites and the shared daily budget."""

    def __init__(self, cap_s):
        self.cap = cap_s
        self.station = {}
        self.sat = {}
        self.day = {}

    @staticmethod
    def _clash(items, a, b):
        return any(a < y and b > x for x, y, _ in items)

    def can(self, station, sat, a, b):
        if self._clash(self.station.get(station, ()), a, b):
            return False
        if self._clash(self.sat.get(sat, ()), a, b):
            return False
        return all(self.day.get(d, 0.0) + s <= self.cap + 1e-6 for d, s in _day_slices(a, b))

    def add(self, station, sat, a, b, tag):
        self.station.setdefault(station, []).append((a, b, tag))
        self.sat.setdefault(sat, []).append((a, b, tag))
        for d, s in _day_slices(a, b):
            self.day[d] = self.day.get(d, 0.0) + s

    def remove(self, station, sat, a, b, tag):
        self.station[station].remove((a, b, tag))
        self.sat[sat].remove((a, b, tag))
        for d, s in _day_slices(a, b):
            self.day[d] -= s

    def longest_budget(self, a, desired):
        """Longest contiguous reservation from ``a`` (<= desired) the daily budget allows."""
        total, cur = 0.0, a
        end = a + timedelta(seconds=desired)
        while cur < end:
            nxt = min(end, _midnight_after(cur))
            room = self.cap - self.day.get(cur.date().isoformat(), 0.0)
            take = min((nxt - cur).total_seconds(), max(0.0, room))
            total += take
            if take < (nxt - cur).total_seconds() - 1e-9:
                break
            cur = nxt
        return total


class _Limit(Exception):
    pass


def _starts(wins, t_min, res, step, origin, latest_first=False):
    """Grid start times of a reservation of ``res`` seconds inside the windows."""
    out = []
    for station, a, b in wins:
        lo = max(a, t_min)
        k = math.ceil((lo - origin).total_seconds() / step - 1e-9)
        s = origin + timedelta(seconds=k * step)
        while s + timedelta(seconds=res) <= b:
            out.append((s, station))
            s += timedelta(seconds=step)
    out.sort(reverse=latest_first)
    return out


def _cover(sats, wins_by_sat, ledger, t_min, res, step, origin, node_limit, latest_first=True):
    """Exact (grid) search for one minimum reservation per satellite.

    Returns (verdict, anchors) with verdict FEASIBLE, INFEASIBLE (search exhausted,
    proven on the grid) or UNDETERMINED (node limit reached).
    """
    order = sorted(sats, key=lambda s: (len(_starts(wins_by_sat.get(s, ()), t_min, res, step, origin)), s))
    nodes = [0]
    placed = []
    dur = timedelta(seconds=res)

    def rec(i):
        if i == len(order):
            return True
        sat = order[i]
        for s, station in _starts(wins_by_sat.get(sat, ()), t_min, res, step, origin, latest_first):
            nodes[0] += 1
            if nodes[0] > node_limit:
                raise _Limit
            if ledger.can(station, sat, s, s + dur):
                tag = "anchor"
                ledger.add(station, sat, s, s + dur, tag)
                placed.append((sat, station, s))
                if rec(i + 1):
                    return True
                placed.pop()
                ledger.remove(station, sat, s, s + dur, tag)
        return False

    try:
        ok = rec(0)
    except _Limit:
        for sat, station, s in placed:
            ledger.remove(station, sat, s, s + dur, "anchor")
        return "UNDETERMINED", []
    if ok:
        return "FEASIBLE", list(placed)
    return "INFEASIBLE", []


def _greedy_anchors(sats, wins_by_sat, ledger, t_min, res, step, origin):
    """Best effort when full coverage is not possible: as many satellites as fit."""
    dur = timedelta(seconds=res)
    order = sorted(sats, key=lambda s: (len(_starts(wins_by_sat.get(s, ()), t_min, res, step, origin)), s))
    placed = []
    for sat in order:
        for s, station in _starts(wins_by_sat.get(sat, ()), t_min, res, step, origin, True):
            if ledger.can(station, sat, s, s + dur):
                ledger.add(station, sat, s, s + dur, "anchor")
                placed.append((sat, station, s))
                break
    return placed


def _merge_gap_hours(wins, start, end):
    spans = sorted((max(a, start), min(b, end)) for _, a, b in wins if b > start and a < end)
    cursor, gap = start, 0.0
    for a, b in spans:
        if a > cursor:
            gap = max(gap, (a - cursor).total_seconds() / 3600)
        cursor = max(cursor, b)
    return max(gap, max(0.0, (end - cursor).total_seconds() / 3600))


def diagnose_coverage(sats, geometric, available, start, end, res_s, cap_s, verdict):
    """Why a satellite cannot be given even one minimum-length contact."""
    per_sat, reasons = {}, []
    days = {}
    t = start
    while t < end:
        d = t.date().isoformat()
        days[d] = min(cap_s, days.get(d, 0.0) + (min(end, _midnight_after(t)) - t).total_seconds())
        t = _midnight_after(t)
    budget_total = sum(days.values())
    for sat in sats:
        longest_geo = max([(min(b, end) - max(a, start)).total_seconds() for _, a, b in geometric.get(sat, ())] or [0])
        longest_av = max([(min(b, end) - max(a, start)).total_seconds() for _, a, b in available.get(sat, ())] or [0])
        if longest_geo < res_s:
            cause = "GEOMETRY"
        elif longest_av < res_s:
            cause = "STATION_AVAILABILITY"
        else:
            cause = None
        per_sat[sat] = {"longest_window_hours": round(longest_geo / 3600, 3),
                        "longest_available_window_hours": round(longest_av / 3600, 3),
                        "individual_constraint": cause}
        if cause:
            reasons.append({"satellite": sat, "constraint": cause,
                            "detail": f"no window of at least {res_s/60:.0f} min"})
    need = len(sats) * res_s
    if need > budget_total + 1e-6:
        reasons.append({"constraint": "DAILY_BUDGET",
                        "detail": f"{len(sats)} minimum contacts need {need/3600:.2f} h, "
                                  f"budget over the horizon is {budget_total/3600:.2f} h"})
    if verdict == "INFEASIBLE" and not reasons:
        reasons.append({"constraint": "STATION_CONFLICT",
                        "detail": "geometry, availability and total budget allow each satellite alone, "
                                  "but no conflict-free combination exists on the time grid"})
    if verdict == "UNDETERMINED":
        reasons.append({"constraint": "SEARCH_LIMIT",
                        "detail": "search limit reached: neither a solution nor infeasibility was proven"})
    return {"per_satellite": per_sat, "binding_constraints": reasons,
            "budget_hours_available": round(budget_total / 3600, 3),
            "minimum_contact_hours_total": round(need / 3600, 3)}


def schedule_contacts(windows, streams, *, start, end, gross_bps, overhead, prep_s, teardown_s,
                      min_tx_s, daily_cap_s, step_s=300, geometric_windows=None,
                      node_limit=200000):
    """Return ``{"contacts": [...], "diagnostics": {...}}``.

    windows: dicts with satellite, station, start, end (UTC datetimes), already
        restricted to what the station can offer. ``geometric_windows`` (optional)
        are the unrestricted visibilities, used only to tell geometry from
        availability in the diagnostics.
    streams: dicts name, rate_bps, priority (1-5), deadline_hours.
    """
    start, end = _utc(start), _utc(end)
    if end <= start or step_s <= 0 or daily_cap_s < 0 or min_tx_s <= 0 or prep_s < 0 or teardown_s < 0:
        raise ValueError("Invalid scheduling parameters")
    if not 0 <= overhead < 1 or gross_bps <= 0:
        raise ValueError("Invalid link assumptions")
    if not streams:
        raise ValueError("Streams required")
    eff = gross_bps * (1 - overhead)
    res_min = prep_s + min_tx_s + teardown_s
    sats = sorted({w["satellite"] for w in windows} | {w["satellite"] for w in (geometric_windows or [])})
    wins_by_sat, geo_by_sat = {}, {}
    for w in windows:
        a, b = max(_utc(w["start"]), start), min(_utc(w["end"]), end)
        if b > a:
            wins_by_sat.setdefault(w["satellite"], []).append((w["station"], a, b))
    for w in (geometric_windows if geometric_windows is not None else windows):
        a, b = max(_utc(w["start"]), start), min(_utc(w["end"]), end)
        if b > a:
            geo_by_sat.setdefault(w["satellite"], []).append((w["station"], a, b))
    rates = {s["name"]: float(s["rate_bps"]) for s in streams}
    total_rate = sum(rates.values())
    ledger = _Ledger(daily_cap_s)

    # ---- coverage guard -------------------------------------------------
    verdict, anchors = _cover(sats, wins_by_sat, ledger, start, res_min, step_s, start, node_limit)
    coverage = {"initial_feasibility": verdict, "anchors_used": 0}
    if verdict != "FEASIBLE":
        anchors = _greedy_anchors(sats, wins_by_sat, ledger, start, res_min, step_s, start)
        coverage["fallback"] = "BEST_EFFORT_PARTIAL_COVERAGE"
        coverage["analysis"] = diagnose_coverage(sats, geo_by_sat, wins_by_sat, start, end, res_min,
                                                 daily_cap_s, verdict)
    anchor_by_sat = {s: (st, a) for s, st, a in anchors}

    # ---- rolling scheduler ----------------------------------------------
    backlog = {s: {n: 0.0 for n in rates} for s in sats}
    usable_s = {s: 0.0 for s in sats}
    served = {s: False for s in sats}
    active = {}
    contacts = []

    def slack_h(sat):
        vals = [(float(st["deadline_hours"]) - backlog[sat][st["name"]] / (rates[st["name"]] * 3600),
                 int(st["priority"])) for st in streams if rates[st["name"]] > 0]
        return vals

    def commit(sat, station, a, res_s, reason):
        b = a + timedelta(seconds=res_s)
        ledger.add(station, sat, a, b, "contact")
        tx_a, tx_b = a + timedelta(seconds=prep_s), b - timedelta(seconds=teardown_s)
        active[sat] = {"satellite": sat, "station": station, "start": a, "end": b,
                       "tx_start": tx_a, "tx_end": tx_b, "reason": reason}
        usable_s[sat] += (tx_b - tx_a).total_seconds()
        served[sat] = True

    t = start
    while t < end:
        dt = min(step_s, (end - t).total_seconds())
        # ---- decisions at time t -------------------------------------
        free = [s for s in sats if s not in active]
        # fire anchors that reach their start
        for sat in list(anchor_by_sat):
            st, a0 = anchor_by_sat[sat]
            if sat in active or served[sat] or a0 > t:
                continue
            if a0 <= t:
                dur = res_min
                ledger.remove(st, sat, a0, a0 + timedelta(seconds=dur), "anchor")
                anchor_by_sat.pop(sat)
                commit(sat, st, a0, dur, "coverage_guard")
                if sat in free:
                    free.remove(sat)
        cands = []
        for sat in free:
            vals = slack_h(sat)
            min_slack = min((v for v, _ in vals), default=float("inf"))
            total_bits = sum(backlog[sat].values())
            lead_h = res_min / 3600
            critical_prios = [p for v, p in vals if v <= lead_h]
            worthwhile = total_bits >= min_tx_s * eff or bool(critical_prios)
            if not worthwhile:
                continue
            if critical_prios:
                key = (0, -max(critical_prios), min_slack, usable_s[sat], sat)
            else:
                key = (1, usable_s[sat], min_slack, 0, sat)
            cands.append((key, sat))
        for key, sat in sorted(cands):
            if sat in active:
                continue
            total_bits = sum(backlog[sat].values())
            net = max(eff - total_rate, eff * 0.05)
            tx_need = max(min_tx_s, (total_bits + total_rate * prep_s) / net)
            desired = prep_s + tx_need + teardown_s
            own = anchor_by_sat.get(sat)
            if own:
                ledger.remove(own[0], sat, own[1], own[1] + timedelta(seconds=res_min), "anchor")
            best = None
            for station, a, b in wins_by_sat.get(sat, ()):
                if not (a <= t and t + timedelta(seconds=res_min) <= b):
                    continue
                room = min((b - t).total_seconds(), (end - t).total_seconds(), desired)
                room = min(room, ledger.longest_budget(t, room))
                if room < res_min - 1e-6:
                    continue
                # keep room for other satellites' anchors: shrink until compatible
                length = room
                while length >= res_min - 1e-6 and not ledger.can(station, sat, t, t + timedelta(seconds=length)):
                    length -= step_s
                if length < res_min - 1e-6:
                    continue
                score = ((b - t).total_seconds(), station)
                if best is None or score > best[0]:
                    best = (score, station, length)
            if best is None:
                if own:
                    ledger.add(own[0], sat, own[1], own[1] + timedelta(seconds=res_min), "anchor")
                continue
            _, station, length = best
            if own:
                anchor_by_sat.pop(sat, None)
            commit(sat, station, t, length, "critical_deadline" if key[0] == 0 else "equitable_share")
        # ---- advance state over [t, t+dt] ------------------------------
        t2 = t + timedelta(seconds=dt)
        for sat in sats:
            for n, r in rates.items():
                backlog[sat][n] += r * dt
        for sat, c in list(active.items()):
            overlap = max(0.0, (min(t2, c["tx_end"]) - max(t, c["tx_start"])).total_seconds())
            cap_bits = eff * overlap
            if cap_bits > 0:
                order = sorted(streams, key=lambda st: (float(st["deadline_hours"]) -
                               (backlog[sat][st["name"]] / (rates[st["name"]] * 3600) if rates[st["name"]] > 0 else 0),
                               -int(st["priority"]), st["name"]))
                for st in order:
                    take = min(cap_bits, backlog[sat][st["name"]])
                    backlog[sat][st["name"]] -= take
                    cap_bits -= take
            if t2 >= c["end"]:
                contacts.append(c)
                del active[sat]
        t = t2
    contacts.extend(active.values())
    contacts.sort(key=lambda c: (c["start"], c["station"], c["satellite"]))

    # ---- report ---------------------------------------------------------
    rows = []
    for c in contacts:
        rows.append({"satellite": c["satellite"], "station": c["station"], "start": c["start"], "end": c["end"],
                     "seconds": (c["end"] - c["start"]).total_seconds(),
                     "tx_start": c["tx_start"], "tx_end": c["tx_end"],
                     "usable_seconds": (c["tx_end"] - c["tx_start"]).total_seconds(),
                     "reason": c["reason"], "status": STATUS})
    per = {s: {"contacts": 0, "reserved_hours": 0.0, "usable_hours": 0.0} for s in sats}
    for r in rows:
        p = per[r["satellite"]]
        p["contacts"] += 1
        p["reserved_hours"] += r["seconds"] / 3600
        p["usable_hours"] += r["usable_seconds"] / 3600
    for p in per.values():
        p["reserved_hours"] = round(p["reserved_hours"], 4)
        p["usable_hours"] = round(p["usable_hours"], 4)
    shares = [p["usable_hours"] for p in per.values()]
    jain = (sum(shares) ** 2) / (len(shares) * sum(x * x for x in shares)) if sum(x * x for x in shares) else None
    budget_used = {d: round(v / 3600, 4) for d, v in sorted(ledger.day.items())}
    reserved_total = sum(r["seconds"] for r in rows)
    usable_total = sum(r["usable_seconds"] for r in rows)
    uncovered = [s for s in sats if per[s]["contacts"] == 0]
    coverage["satellites_without_contact"] = uncovered
    coverage["all_satellites_covered"] = not uncovered
    coverage["anchors_used"] = sum(1 for r in rows if r["reason"] == "coverage_guard")
    if uncovered and "analysis" not in coverage:
        coverage["analysis"] = diagnose_coverage(sats, geo_by_sat, wins_by_sat, start, end, res_min,
                                                 daily_cap_s, "UNDETERMINED")
    return {"contacts": rows,
            "diagnostics": {"status": STATUS, "policy": {"preparation_seconds": prep_s,
                                                          "teardown_seconds": teardown_s,
                                                          "minimum_useful_tx_seconds": min_tx_s,
                                                          "daily_cap_hours": daily_cap_s / 3600,
                                                          "step_seconds": step_s},
                            "coverage": coverage, "per_satellite": per,
                            "jain_fairness_usable_time": jain,
                            "usable_fraction_of_reserved_time": (usable_total / reserved_total) if reserved_total else None,
                            "method": "deterministic heuristic (coverage guard + critical-first + equity); "
                                      "not a proven optimum",
                            "daily_budget_used_hours": budget_used,
                            "budget_used_hours_total": round(sum(ledger.day.values()) / 3600, 4),
                            "visibility_note": "Visibility windows are historical (2020) or calendar-shifted; "
                                               "they are NOT confirmed DSN availability for 2030."}}


def explain_unmet_deadlines(streams, windows, start, end, *, delivery, prep_s, teardown_s,
                            min_tx_s, daily_cap_s, gross_bps, overhead, size_rate_result=None):
    """Which constraint explains deadlines that are still not met?

    Structural lower-bound analysis (independent of the concrete calendar): it
    compares the minimum reservation time the tightest deadline demands with the
    budget, the geometric gaps with the deadlines, and uses the rate-sizing result
    to separate a rate problem from a contact-time problem.
    """
    start, end = _utc(start), _utc(end)
    horizon_h = (end - start).total_seconds() / 3600
    eff = gross_bps * (1 - overhead)
    sats = sorted({w["satellite"] for w in windows})
    d_min = min(float(s["deadline_hours"]) for s in streams if float(s["rate_bps"]) > 0)
    total_rate = sum(float(s["rate_bps"]) for s in streams)
    passes_per_sat = max(1, math.floor(horizon_h / d_min))
    tx_each = max(min_tx_s, total_rate * d_min * 3600 / eff)
    needed_s = len(sats) * passes_per_sat * (prep_s + tx_each + teardown_s)
    days = {}
    t = start
    while t < end:
        d = t.date().isoformat()
        days[d] = min(daily_cap_s, days.get(d, 0.0) + (min(end, _midnight_after(t)) - t).total_seconds())
        t = _midnight_after(t)
    budget_s = sum(days.values())
    geo = {}
    for w in windows:
        geo.setdefault(w["satellite"], []).append((w["station"], _utc(w.get("start", w.get("start_utc"))),
                                                   _utc(w.get("end", w.get("end_utc")))))
    max_gap = max((_merge_gap_hours(v, start, end) for v in geo.values()), default=0.0)
    findings = []
    if delivery.get("all_deadlines_met"):
        return {"all_deadlines_met": True, "findings": []}
    findings.append({"constraint": "DAILY_BUDGET" if needed_s > budget_s else "NOT_BUDGET_LIMITED",
                     "detail": f"holding the tightest deadline ({d_min:g} h) for {len(sats)} satellites over "
                               f"{horizon_h:.1f} h needs at least {passes_per_sat} passes each, "
                               f"{needed_s/3600:.1f} h of reserved time (pass overhead "
                               f"{(prep_s+teardown_s)/60:.0f} min each); the budget is {budget_s/3600:.1f} h",
                     "required_hours": round(needed_s / 3600, 2), "available_hours": round(budget_s / 3600, 2)})
    findings.append({"constraint": "GEOMETRY" if max_gap > d_min else "NOT_GEOMETRY_LIMITED",
                     "detail": f"largest gap with no station in view for any satellite: {max_gap:.2f} h "
                               f"(tightest deadline {d_min:g} h)"})
    if size_rate_result is not None:
        if size_rate_result["status"] == "INFEASIBLE_WITH_GIVEN_GRANTS":
            findings.append({"constraint": "CONTACT_TIME_NOT_RATE",
                             "detail": "deadlines stay unmet even with a very high gross rate: the granted "
                                       "contact time/cadence is insufficient, not the transmission rate"})
        else:
            req = size_rate_result["required_gross_bps"]
            findings.append({"constraint": "TRANSMISSION_RATE" if req > gross_bps else "NOT_RATE_LIMITED",
                             "detail": f"minimum gross rate that meets all deadlines with this schedule: "
                                       f"{req:,.0f} bps (scenario rate {gross_bps:,.0f} bps)"})
    findings.append({"constraint": "AVAILABILITY", "detail": "no station outage is modelled; real DSN availability "
                                                              "is unknown and unconfirmed"})
    return {"all_deadlines_met": False, "findings": findings}
