"""PDR inputs taken directly from the pipeline results (no recomputation).

``load(output_dir)`` returns the tables the report needs; ``plot_figures`` draws

* memory occupancy by subsystem over time (shared pool, logical queues),
* downloaded data by subsystem and satellite,
* the DSN contacts actually used (assigned contacts, not candidate windows).

Everything comes from ``memory_queues.csv``, ``downloaded_by_subsystem.csv``,
``assigned_contacts.csv`` and ``memory_queues_summary.json`` written by
``dsn_pipeline`` / ``integrated_preliminary``. Figures are labelled as
preliminary: 2020 windows are not confirmed DSN availability for 2030.
"""
import csv
import json
from datetime import datetime
from pathlib import Path

CAVEAT = ("Preliminary: hypothetical allocation, not DSN bookings; historical (2020) or calendar-shifted "
          "visibility is not confirmed availability for 2030; memory/threshold values are scenario values.")


def _rows(path):
    p = Path(path)
    if not p.exists():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load(output_dir):
    out = Path(output_dir)
    summary_path = out / "memory_queues_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    return {"memory_curves": _rows(out / "memory_queues.csv"),
            "downloaded_by_subsystem": _rows(out / "downloaded_by_subsystem.csv"),
            "assigned_contacts": _rows(out / "assigned_contacts.csv"),
            "summary": summary,
            "requirements": None if summary is None else summary["requirements"],
            "conservation": None if summary is None else summary["conservation"],
            "caveat": CAVEAT}


def plot_figures(output_dir, figures_dir=None):
    """Write PNG figures; returns {"status", "files"}."""
    data = load(output_dir)
    if data["summary"] is None:
        return {"status": "NO_RESULTS", "files": []}
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return {"status": "MATPLOTLIB_NOT_INSTALLED", "files": []}
    figs = Path(figures_dir or Path(output_dir) / "figures")
    figs.mkdir(parents=True, exist_ok=True)
    files = []
    mem = data["summary"]["memory"]
    by_sat = {}
    for r in data["memory_curves"]:
        by_sat.setdefault(r["satellite"], {}).setdefault(r["stream"], []).append(
            (datetime.fromisoformat(r["time_utc"]), float(r["queued_mbit"])))
    for sat, streams in sorted(by_sat.items()):
        names = sorted(streams)
        times = [t for t, _ in streams[names[0]]]
        fig, ax = plt.subplots(figsize=(11, 4.5))
        ax.stackplot(times, [[v for _, v in streams[n]] for n in names], labels=names)
        ax.axhline(mem["capacity_mbit"], color="k", ls="--", lw=1, label=f"capacity {mem['capacity_mbit']:g} Mbit")
        ax.axhline(mem["usable_mbit"], color="r", ls=":", lw=1, label=f"usable {mem['usable_mbit']:g} Mbit")
        ax.set_ylabel("Queued data (Mbit)")
        ax.set_title(f"{sat}: shared OBDH memory by subsystem (logical queues)")
        ax.legend(loc="upper left", fontsize=7, ncol=3)
        fig.text(0.01, 0.005, CAVEAT, fontsize=6)
        fig.tight_layout(rect=(0, 0.02, 1, 1))
        f = figs / f"memory_by_subsystem_{sat}.png"
        fig.savefig(f, dpi=130)
        plt.close(fig)
        files.append(str(f))
    rows = data["downloaded_by_subsystem"]
    if rows:
        sats = sorted({r["satellite"] for r in rows})
        names = sorted({r["stream"] for r in rows})
        fig, ax = plt.subplots(figsize=(10, 4.5))
        bottom = [0.0] * len(sats)
        for n in names:
            vals = [sum(float(r["downloaded_mbit"]) for r in rows if r["satellite"] == s and r["stream"] == n) for s in sats]
            ax.bar(sats, vals, bottom=bottom, label=n)
            bottom = [b + v for b, v in zip(bottom, vals)]
        ax.set_ylabel("Downloaded (Mbit)")
        ax.set_title("Downloaded data by subsystem")
        ax.legend(fontsize=7, ncol=3)
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        fig.text(0.01, 0.005, CAVEAT, fontsize=6)
        fig.tight_layout(rect=(0, 0.03, 1, 1))
        f = figs / "downloaded_by_subsystem.png"
        fig.savefig(f, dpi=130)
        plt.close(fig)
        files.append(str(f))
    contacts = data["assigned_contacts"]
    if contacts:
        sats = sorted({c["satellite"] for c in contacts})
        fig, ax = plt.subplots(figsize=(11, 4.5))
        for c in contacts:
            a, b = datetime.fromisoformat(c["start_utc"]), datetime.fromisoformat(c["end_utc"])
            ta, tb = datetime.fromisoformat(c["tx_start_utc"]), datetime.fromisoformat(c["tx_end_utc"])
            y = sats.index(c["satellite"])
            ax.barh(y, (b - a).total_seconds() / 86400, left=matplotlib.dates.date2num(a), color="0.75", height=0.6)
            ax.barh(y, (tb - ta).total_seconds() / 86400, left=matplotlib.dates.date2num(ta), color="tab:blue", height=0.6)
        ax.set_yticks(range(len(sats)))
        ax.set_yticklabels(sats)
        ax.xaxis_date()
        fig.autofmt_xdate()
        ax.set_title("Assigned DSN contacts (grey: reservation, blue: useful transmission)")
        fig.text(0.01, 0.005, CAVEAT, fontsize=6)
        fig.tight_layout(rect=(0, 0.03, 1, 1))
        f = figs / "dsn_contacts_used.png"
        fig.savefig(f, dpi=130)
        plt.close(fig)
        files.append(str(f))
    return {"status": "OK", "files": files, "caveat": CAVEAT}
