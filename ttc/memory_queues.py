"""Logical per-subsystem queues inside each satellite's shared OBDH memory.

Model (preliminary, nothing fitted)
    * One OBDH memory per satellite (independent), shared by all subsystems:
      there are NO physical partitions or fixed quotas per subsystem.
    * Inside it, data are organised logically as one FIFO queue per stream with
      priority, age of the oldest bit and maximum delivery age. The queue order
      used for downlink is the one of ``ground_delivery.simulate``: earliest
      deadline first, priority as tie breaker.
    * Telemetry is never dropped or reduced; the queues only account where the
      occupied memory belongs and which data must leave first.

Capacity, reserve and thresholds come from ``data/adaptive_storage_scenario.json``
(1024 Mbit per satellite, 15 % reserve, watch/urgent/critical 70/85/95 %,
preventive trigger 65 %). They are simulation values, NOT approved requirements
and NOT a selected physical memory device.
"""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = "LOGICAL_QUEUES_IN_SHARED_MEMORY_PRELIMINARY"
CONTACT_SOURCE = "ASSIGNED_CONTACTS_FROM_ttc.dsn_scheduler"
TOL_MBIT = 1e-6  # one bit


def _dt(v):
    if isinstance(v, str):
        v = datetime.fromisoformat(v.replace("Z", "+00:00"))
    return v.astimezone(timezone.utc)


def _ov(a, b, c, d):
    return max(0.0, (min(b, d) - max(a, c)).total_seconds())


def _window(w):
    return (w["satellite"], w["station"], _dt(w.get("start", w.get("start_utc"))), _dt(w.get("end", w.get("end_utc"))))


def load_memory_config(path=None):
    cfg = json.loads(Path(path or ROOT / "data" / "adaptive_storage_scenario.json").read_text(encoding="utf-8"))
    cap = float(cfg["memory_capacity_mbit_per_satellite"])
    reserve = float(cfg["memory_reserve_fraction"])
    thr = list(cfg["warning_thresholds"])
    if cap <= 0 or not 0 <= reserve < 1 or sorted(thr) != thr or any(not 0 < x < 1 for x in thr):
        raise ValueError("Invalid memory configuration")
    return {"capacity_mbit": cap, "reserve_fraction": reserve,
            "usable_mbit": cap * (1 - reserve), "reserve_mbit": cap * reserve,
            "warning_thresholds": thr, "proactive_trigger_fraction": float(cfg["proactive_trigger_fraction"])}


class QueueObserver:
    """Read-only observer for ``ground_delivery.simulate(observer=...)``."""

    def __init__(self, streams, start, config, sample_seconds=1800, contacts=None,
                 visibility=None, min_tx_s=None, satellites=None):
        """``contacts``: ASSIGNED contacts (dicts satellite, station, start, end,
        tx_start, tx_end). None = contact accounting disabled; [] = no contact was
        assigned (a requirement failure for every satellite)."""
        self.streams = {s["name"]: s for s in streams}
        self.cfg = config
        self.start = _dt(start)
        self.sample = sample_seconds
        self.rows = []
        self.stats = {}
        self._last_sample = {}
        self._prev_t = {}
        self._state = {}
        self._max_dt = 0.0
        self.visibility = None if visibility is None else [_window(w) for w in visibility]
        self.min_tx_s = min_tx_s
        self.track_contacts = contacts is not None
        self.records = {}
        self.unattributed = {}
        for c in (contacts or []):
            rec = {"satellite": c["satellite"], "station": c["station"], "start": _dt(c["start"]),
                   "end": _dt(c["end"]), "tx_start": _dt(c["tx_start"]), "tx_end": _dt(c["tx_end"]),
                   "reason": c.get("reason"), "backlog_start": None, "backlog_tx_start": None,
                   "backlog_end": None, "backlog_tx_end": None, "generated": {n: 0.0 for n in self.streams},
                   "downloaded": {n: 0.0 for n in self.streams}}
            self.records.setdefault(c["satellite"], []).append(rec)
        for recs in self.records.values():
            recs.sort(key=lambda r: r["start"])
        self.sats_expected = sorted(set(satellites or ()) | {w[0] for w in (self.visibility or ())} | set(self.records))
        self.cut_times = sorted({x for recs in self.records.values() for r in recs
                                 for x in (r["start"], r["end"], r["tx_start"], r["tx_end"])})

    def _stat(self, sat):
        return self.stats.setdefault(sat, {
            "peak_total_bits": 0.0, "peak_time": None, "peak_by_stream_at_total_peak": {},
            "peak_by_stream_bits": {n: 0.0 for n in self.streams},
            "max_age_h": {n: 0.0 for n in self.streams},
            "bit_seconds": {n: 0.0 for n in self.streams}, "elapsed_s": 0.0,
            "first_crossing": {}, "seconds_above": {}})

    def __call__(self, sat, t, backlog, oldest, taken):
        st = self._stat(sat)
        prev = self._prev_t.get(sat, self.start)
        dt = (t - prev).total_seconds()
        self._prev_t[sat] = t
        self._max_dt = max(self._max_dt, dt)
        if self.track_contacts:
            self._account_contacts(sat, prev, t, backlog, taken)
        self._state[sat] = {n: v for n, v in backlog.items()}
        total = sum(backlog.values())
        st["elapsed_s"] += dt
        cap = self.cfg["capacity_mbit"] * 1e6
        levels = {"proactive_trigger": self.cfg["proactive_trigger_fraction"],
                  "watch": self.cfg["warning_thresholds"][0], "urgent": self.cfg["warning_thresholds"][1],
                  "critical": self.cfg["warning_thresholds"][2],
                  "usable_limit": 1 - self.cfg["reserve_fraction"]}
        for name, frac in levels.items():
            if total >= frac * cap:
                st["first_crossing"].setdefault(name, t.isoformat())
                st["seconds_above"][name] = st["seconds_above"].get(name, 0.0) + dt
        if total > st["peak_total_bits"]:
            st["peak_total_bits"], st["peak_time"] = total, t.isoformat()
            st["peak_by_stream_at_total_peak"] = dict(backlog)
        ages = {}
        for n in self.streams:
            st["peak_by_stream_bits"][n] = max(st["peak_by_stream_bits"][n], backlog[n])
            st["bit_seconds"][n] += backlog[n] * dt
            age = (t - oldest[n]).total_seconds() / 3600 if oldest[n] is not None else 0.0
            ages[n] = age
            st["max_age_h"][n] = max(st["max_age_h"][n], age)
        last = self._last_sample.get(sat)
        if last is None or (t - last).total_seconds() >= self.sample:
            self._last_sample[sat] = t
            for n, s in self.streams.items():
                self.rows.append({"satellite": sat, "time_utc": t.isoformat(), "stream": n,
                                  "priority": int(s["priority"]), "max_age_hours": float(s["deadline_hours"]),
                                  "queued_mbit": round(backlog[n] / 1e6, 6),
                                  "oldest_age_hours": round(ages[n], 4),
                                  "sent_in_step_mbit": round(taken.get(n, 0.0) / 1e6, 6),
                                  "total_occupancy_fraction": round(total / cap, 5)})

    def _account_contacts(self, sat, prev, t, backlog, taken):
        """Attribute generation, backlog snapshots and downloads to assigned contacts.

        Snapshots use the end-of-previous-step state, exact when contact
        boundaries lie on simulation steps (the scheduler grid does)."""
        last = self._state.get(sat) or {n: 0.0 for n in self.streams}
        recs = self.records.get(sat, [])
        best, best_ov = None, 0.0
        for r in recs:
            if r["backlog_start"] is None and t > r["start"]:
                r["backlog_start"] = dict(last)
            if r["backlog_tx_start"] is None and t > r["tx_start"]:
                r["backlog_tx_start"] = dict(last)
            ov = _ov(prev, t, r["start"], r["end"])
            if ov > 0:
                for n, s in self.streams.items():
                    r["generated"][n] += float(s["rate_bps"]) * ov
            if r["backlog_tx_end"] is None and t >= r["tx_end"]:
                r["backlog_tx_end"] = dict(backlog)
            if r["backlog_end"] is None and t >= r["end"]:
                r["backlog_end"] = dict(backlog)
            tov = _ov(prev, t, r["tx_start"], r["tx_end"])
            if tov > best_ov:
                best, best_ov = r, tov
        if taken:
            if best is None:
                u = self.unattributed.setdefault(sat, {n: 0.0 for n in self.streams})
                for n, v in taken.items():
                    u[n] += v
            else:
                for n, v in taken.items():
                    best["downloaded"][n] += v

    def _finalize_contacts(self):
        for sat, recs in self.records.items():
            final = self._state.get(sat, {n: 0.0 for n in self.streams})
            for r in recs:
                for key in ("backlog_start", "backlog_tx_start", "backlog_tx_end", "backlog_end"):
                    if r[key] is None:
                        r[key] = dict(final)

    def contact_rows(self):
        """Assigned contacts with data accounting (Mbit)."""
        self._finalize_contacts()
        rows = []
        for sat, recs in sorted(self.records.items()):
            for r in recs:
                m = lambda d: {n: v / 1e6 for n, v in d.items()}
                b0, b1, g, dl, b2 = (m(r["backlog_start"]), m(r["backlog_tx_start"]), m(r["generated"]),
                                     m(r["downloaded"]), m(r["backlog_end"]))
                b3 = m(r["backlog_tx_end"])
                resid = sum(b0.values()) + sum(g.values()) - sum(dl.values()) - sum(b2.values())
                rows.append({
                    "satellite": sat, "station": r["station"],
                    "start_utc": r["start"].isoformat(), "end_utc": r["end"].isoformat(),
                    "reserved_minutes": round((r["end"] - r["start"]).total_seconds() / 60, 4),
                    "tx_start_utc": r["tx_start"].isoformat(), "tx_end_utc": r["tx_end"].isoformat(),
                    "useful_tx_minutes": round(max(0.0, (r["tx_end"] - r["tx_start"]).total_seconds()) / 60, 4),
                    "reason": r["reason"],
                    "backlog_at_start_mbit": round(sum(b0.values()), 6),
                    "backlog_at_tx_start_mbit": round(sum(b1.values()), 6),
                    "generated_during_contact_mbit": round(sum(g.values()), 6),
                    "downloaded_mbit": round(sum(dl.values()), 6),
                    "backlog_after_mbit": round(sum(b2.values()), 6),
                    "backlog_after_tx_mbit": round(sum(b3.values()), 6),
                    "backlog_drained": sum(b2.values()) < 1e-6,
                    "backlog_drained_at_tx_end": sum(b3.values()) < 1e-3,
                    "balance_residual_mbit": round(resid, 9),
                    "backlog_at_start_by_stream_mbit": {n: round(v, 6) for n, v in b0.items()},
                    "generated_during_contact_by_stream_mbit": {n: round(v, 6) for n, v in g.items()},
                    "downloaded_by_stream_mbit": {n: round(v, 6) for n, v in dl.items()},
                    "backlog_after_by_stream_mbit": {n: round(v, 6) for n, v in b2.items()},
                    "status": "ASSIGNED_CONTACT_NOT_DSN_BOOKING"})
        rows.sort(key=lambda x: (x["start_utc"], x["station"], x["satellite"]))
        return rows

    def requirement_failures(self, delivery):
        """Explicit failures: lost/overflowing data, missed deadlines, bad contacts."""
        cap = self.cfg["capacity_mbit"]
        usable = self.cfg["usable_mbit"]
        out = []

        def fail(code, detail, sat=None, stream=None, **extra):
            out.append({"code": code, "satellite": sat, "stream": stream, "detail": detail,
                        "severity": "REQUIREMENT_FAILURE", **extra})

        for sat, st in sorted(self.stats.items()):
            d = delivery["satellites"][sat]
            for n, x in d["by_stream"].items():
                res = (x["produced_bits"] - x["delivered_bits"] - x["remaining_bits"]) / 1e6
                if abs(res) > TOL_MBIT:
                    fail("DATA_CONSERVATION_VIOLATION", f"initial + generated - downloaded - final = {res:.9f} Mbit", sat, n)
                expected = float(self.streams[n]["rate_bps"]) * st["elapsed_s"] / 1e6
                if abs(x["produced_bits"] / 1e6 - expected) > 1e-3:
                    fail("DATA_GENERATION_MISMATCH", f"generated {x['produced_bits']/1e6:.6f} Mbit, rate x time {expected:.6f} Mbit", sat, n)
            peak = st["peak_total_bits"] / 1e6
            if peak > cap + TOL_MBIT:
                fail("MEMORY_OVERFLOW", f"peak {peak:.2f} Mbit exceeds capacity {cap:g} Mbit by {peak-cap:.2f} Mbit; "
                     "this data would be lost on a real memory (the model does not drop it)", sat,
                     overflow_mbit=round(peak - cap, 4))
            elif peak > usable + TOL_MBIT:
                fail("MEMORY_RESERVE_EXCEEDED", f"peak {peak:.2f} Mbit uses the reserve (usable {usable:g} Mbit)", sat)
            for ev in d["deadline_events"]:
                fail("DEADLINE_MISSED", f"first age violation at {ev['first_violation_utc']} "
                     f"(maximum age {self.streams[ev['subsystem']]['deadline_hours']:g} h)", sat, ev["subsystem"],
                     first_violation_utc=ev["first_violation_utc"])
        if not self.track_contacts:
            return out
        for sat in self.sats_expected:
            if not self.records.get(sat):
                fail("NO_CONTACT", "no contact was assigned to this satellite", sat)
        for sat, u in self.unattributed.items():
            tot = sum(u.values()) / 1e6
            if tot > TOL_MBIT:
                fail("UNATTRIBUTED_DOWNLOAD", f"{tot:.6f} Mbit downloaded outside any assigned contact", sat)
        tol = 10 * TOL_MBIT  # exact: simulation steps are cut at contact boundaries
        for r in self.contact_rows():
            if abs(r["balance_residual_mbit"]) > tol:
                fail("CONTACT_BALANCE_VIOLATION", f"contact {r['start_utc']}: backlog + generated - downloaded - "
                     f"backlog_after = {r['balance_residual_mbit']} Mbit", r["satellite"])
            if self.min_tx_s is not None and r["useful_tx_minutes"] * 60 < self.min_tx_s - 1e-6:
                fail("CONTACT_BELOW_MINIMUM_TX", f"useful TX {r['useful_tx_minutes']} min is below the minimum", r["satellite"])
        flat = [(sat, r) for sat, recs in self.records.items() for r in recs]
        for key, label in (("station", "STATION"), ("satellite", "SATELLITE")):
            names = {r[key] for _, r in flat}
            for name in sorted(names):
                mine = sorted((r for _, r in flat if r[key] == name), key=lambda r: r["start"])
                for a, b in zip(mine, mine[1:]):
                    if a["end"] > b["start"]:
                        fail(f"CONTACT_OVERLAP_{label}", f"{name}: {a['start'].isoformat()} overlaps {b['start'].isoformat()}",
                             a["satellite"] if key == "satellite" else None)
        if self.visibility is not None:
            for sat, r in flat:
                if not any(w[0] == sat and w[1] == r["station"] and w[2] <= r["start"] and r["end"] <= w[3]
                           for w in self.visibility):
                    fail("CONTACT_OUTSIDE_VISIBILITY", f"{r['station']} {r['start'].isoformat()}", sat)
        return out

    def summary(self, delivery, horizon_hours):
        cap_mbit = self.cfg["capacity_mbit"]
        sats = {}
        for sat, st in sorted(self.stats.items()):
            peak_total = st["peak_total_bits"] / 1e6
            by_stream = {}
            for n, s in self.streams.items():
                by_stream[n] = {
                    "priority": int(s["priority"]), "max_age_hours": float(s["deadline_hours"]),
                    "generated_mbit": round(delivery["satellites"][sat]["by_stream"][n]["produced_bits"] / 1e6, 4),
                    "delivered_mbit": round(delivery["satellites"][sat]["by_stream"][n]["delivered_bits"] / 1e6, 4),
                    "remaining_mbit": round(delivery["satellites"][sat]["by_stream"][n]["remaining_bits"] / 1e6, 4),
                    "peak_queue_mbit": round(st["peak_by_stream_bits"][n] / 1e6, 4),
                    "queue_mbit_at_total_peak": round(st["peak_by_stream_at_total_peak"].get(n, 0.0) / 1e6, 4),
                    "share_of_peak_occupancy": round(st["peak_by_stream_at_total_peak"].get(n, 0.0) / st["peak_total_bits"], 4)
                    if st["peak_total_bits"] else 0.0,
                    "mean_queue_mbit": round(st["bit_seconds"][n] / st["elapsed_s"] / 1e6, 4) if st["elapsed_s"] else 0.0,
                    "max_oldest_age_hours": round(st["max_age_h"][n], 3),
                    "deadline_violated": n in delivery["satellites"][sat]["deadline_violations"]}
            sats[sat] = {"peak_total_mbit": round(peak_total, 4), "peak_time_utc": st["peak_time"],
                         "peak_fraction_of_capacity": round(peak_total / cap_mbit, 5),
                         "peak_fraction_of_usable": round(peak_total / self.cfg["usable_mbit"], 5),
                         "first_threshold_crossing_utc": st["first_crossing"],
                         "hours_above_threshold": {k: round(v / 3600, 3) for k, v in st["seconds_above"].items()},
                         "usable_limit_exceeded": "usable_limit" in st["first_crossing"],
                         "by_stream": by_stream}
        gen = {n: sum(delivery["satellites"][s]["by_stream"][n]["produced_bits"] for s in sats) / 1e6 for n in self.streams}
        total_rate = sum(float(s["rate_bps"]) for s in self.streams.values())
        n_sat = len(sats)
        conservation = {}
        for sat in sats:
            by = delivery["satellites"][sat]["by_stream"]
            streams_c = {n: {"initial_mbit": 0.0, "generated_mbit": round(x["produced_bits"] / 1e6, 6),
                             "downloaded_mbit": round(x["delivered_bits"] / 1e6, 6),
                             "final_mbit": round(x["remaining_bits"] / 1e6, 6),
                             "residual_mbit": round((x["produced_bits"] - x["delivered_bits"] - x["remaining_bits"]) / 1e6, 9)}
                         for n, x in by.items()}
            conservation[sat] = {
                "initial_mbit": 0.0,
                "generated_mbit": round(sum(v["generated_mbit"] for v in streams_c.values()), 6),
                "downloaded_mbit": round(sum(v["downloaded_mbit"] for v in streams_c.values()), 6),
                "final_mbit": round(sum(v["final_mbit"] for v in streams_c.values()), 6),
                "residual_mbit": round(sum(v["residual_mbit"] for v in streams_c.values()), 9),
                "by_stream": streams_c}
        failures = self.requirement_failures(delivery)
        counts = {}
        for f in failures:
            counts[f["code"]] = counts.get(f["code"], 0) + 1
        contacts_out = self.contact_rows() if self.track_contacts else None
        return {"status": STATUS,
                "conservation": {"equation": "M_initial + D_generated = D_downloaded + M_final (per satellite and per subsystem)",
                                 "initial_state": "memory empty at the start of the horizon (simulation assumption)",
                                 "max_abs_residual_mbit": max([abs(c["residual_mbit"]) for c in conservation.values()] +
                                                              [abs(v["residual_mbit"]) for c in conservation.values() for v in c["by_stream"].values()] or [0.0]),
                                 "satellites": conservation},
                "requirements": {"status": "REQUIREMENTS_MET" if not failures else "REQUIREMENTS_NOT_MET",
                                 "failures": failures, "counts_by_code": counts,
                                 "note": "Overflow, loss and missed deadlines are reported as failures; nothing is hidden or reduced."},
                "contact_source": CONTACT_SOURCE if self.track_contacts else None,
                "assigned_contacts": contacts_out,
                "model": "one independent OBDH memory per satellite; shared pool, logical queue per stream; "
                         "no physical partitions or fixed quotas; telemetry is not reduced",
                "download_order_policy": "earliest deadline first (oldest bit + max age), priority as tie breaker, FIFO inside each stream",
                "memory": {"capacity_mbit": cap_mbit, "usable_mbit": round(self.cfg["usable_mbit"], 4),
                           "reserve_mbit": round(self.cfg["reserve_mbit"], 4),
                           "reserve_fraction": self.cfg["reserve_fraction"],
                           "warning_thresholds": self.cfg["warning_thresholds"],
                           "proactive_trigger_fraction": self.cfg["proactive_trigger_fraction"],
                           "note": "capacity/reserve/thresholds are scenario values, not approved requirements nor a selected memory device"},
                "generation": {"per_satellite_bps": round(total_rate, 2),
                               "per_satellite_mbit_per_day": round(total_rate * 86400 / 1e6, 2),
                               "per_satellite_mbit_horizon": round(total_rate * horizon_hours * 3600 / 1e6, 2),
                               "constellation_satellites": n_sat,
                               "constellation_bps": round(total_rate * n_sat, 2),
                               "constellation_mbit_per_day": round(total_rate * n_sat * 86400 / 1e6, 2),
                               "constellation_mbit_horizon": round(total_rate * n_sat * horizon_hours * 3600 / 1e6, 2),
                               "note": "generated data, not downloaded data"},
                "generated_mbit_by_stream_constellation": {n: round(v, 4) for n, v in gen.items()},
                "satellites": sats}


def _write_csv(path, rows, fields=None):
    rows = list(rows)
    fields = fields or (list(rows[0]) if rows else ["satellite"])
    with Path(path).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def requested_duration_rows(contacts):
    """Rows for ``requested_contact_durations.csv`` built ONLY from assigned contacts.

    Candidate visibility windows are never mixed in; the file is the input of the
    antenna / EPS / thermal sizing chain.
    """
    return [{"satellite": c["satellite"], "station": c["station"],
             "reservation_start_utc": c["start_utc"], "reservation_end_utc": c["end_utc"],
             "reserved_minutes": c["reserved_minutes"],
             "assigned_useful_tx_minutes": c["useful_tx_minutes"],
             "backlog_at_start_mbit": c["backlog_at_start_mbit"],
             "backlog_at_tx_start_mbit": c["backlog_at_tx_start_mbit"],
             "generated_during_contact_mbit": c["generated_during_contact_mbit"],
             "downloaded_mbit": c["downloaded_mbit"],
             "backlog_after_mbit": c["backlog_after_mbit"],
             "backlog_after_tx_mbit": c["backlog_after_tx_mbit"],
             "backlog_drained_at_tx_end": c["backlog_drained_at_tx_end"],
             "backlog_drained": c["backlog_drained"],
             "tx_start_utc": c["tx_start_utc"], "tx_end_utc": c["tx_end_utc"],
             "source": CONTACT_SOURCE, "status": c["status"]} for c in contacts]


def write_outputs(observer, delivery, horizon_hours, out_dir):
    """Write the queue / contact / download tables and the JSON summary.

    memory_queues.csv            sampled per-subsystem queue curves
    assigned_contacts.csv        contacts actually assigned, with data accounting
    requested_contact_durations.csv  same contacts, input of the antenna/EPS/thermal chain
    downloaded_by_subsystem.csv  generated / downloaded / remaining per satellite and subsystem
    memory_queues_summary.json   everything, plus conservation and requirement failures
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = observer.summary(delivery, horizon_hours)
    if observer.rows:
        _write_csv(out / "memory_queues.csv", observer.rows)
    dl = [{"satellite": sat, "stream": n, "priority": x["priority"], "max_age_hours": x["max_age_hours"],
           "generated_mbit": x["generated_mbit"], "downloaded_mbit": x["delivered_mbit"],
           "remaining_mbit": x["remaining_mbit"], "peak_queue_mbit": x["peak_queue_mbit"],
           "max_oldest_age_hours": x["max_oldest_age_hours"], "deadline_violated": x["deadline_violated"]}
          for sat, v in summary["satellites"].items() for n, x in v["by_stream"].items()]
    if dl:
        _write_csv(out / "downloaded_by_subsystem.csv", dl)
    contacts = summary["assigned_contacts"]
    if contacts is not None:
        flat = [{k: v for k, v in c.items() if not isinstance(v, dict)} for c in contacts]
        for c, row in zip(contacts, flat):
            for key in ("backlog_at_start_by_stream_mbit", "downloaded_by_stream_mbit"):
                for n, v in c[key].items():
                    row[f"{key.replace('_by_stream_mbit', '')}_{n}_mbit"] = v
        fields = list(flat[0]) if flat else ["satellite", "station", "start_utc", "end_utc"]
        _write_csv(out / "assigned_contacts.csv", flat, fields)
        req = requested_duration_rows(contacts)
        _write_csv(out / "requested_contact_durations.csv", req,
                   list(req[0]) if req else ["satellite", "station", "reservation_start_utc", "assigned_useful_tx_minutes", "source"])
    (out / "memory_queues_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
