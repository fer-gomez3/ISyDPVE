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
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = "LOGICAL_QUEUES_IN_SHARED_MEMORY_PRELIMINARY"


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

    def __init__(self, streams, start, config, sample_seconds=1800):
        self.streams = {s["name"]: s for s in streams}
        self.cfg = config
        self.start = start
        self.sample = sample_seconds
        self.rows = []
        self.stats = {}
        self._last_sample = {}
        self._prev_t = {}

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
        return {"status": STATUS,
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


def write_outputs(observer, delivery, horizon_hours, out_dir):
    """Write ``memory_queues.csv`` (sampled) and ``memory_queues_summary.json``."""
    import csv
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = observer.summary(delivery, horizon_hours)
    if observer.rows:
        with (out / "memory_queues.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(observer.rows[0]))
            w.writeheader()
            w.writerows(observer.rows)
    (out / "memory_queues_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
