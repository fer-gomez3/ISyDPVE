"""One-command SELENA TT&C preliminary pipeline.

Run: python -m ttc.run_preliminary
Writes machine-readable outputs, engineering report and dependency-free SVG plots.
This is a hypothetical DSN scenario, not a validated operational schedule.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path
from .adaptive_storage import ROOT, plan
from .memory_sizing import trade_study
from .hardware_trade import compare
from .antenna_link_budget import evaluate
from .mandatory_link_sizing import size_contacts

def _csv(path):
    with open(path,newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _plot_history(rows,path):
    groups=defaultdict(list)
    for r in rows: groups[r["satellite"]].append(float(r["memory_mbit"]))
    palette=["#2c7fb8","#d95f0e","#31a354","#756bb1","#de2d26","#636363","#1b9e77","#e7298a"]
    width,height=1000,480
    maxlen=max(map(len,groups.values()))
    ymax=max([float(x) for series in groups.values() for x in series]+[1])
    parts=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="white"/>',
           '<text x="65" y="26" font-family="sans-serif" font-size="18">SELENA — OBDH memory by spacecraft (Mbit)</text>',
           '<path d="M65 40 V420 H975" stroke="#333" fill="none"/>']
    for idx,(sat,values) in enumerate(sorted(groups.items())):
        coords=" ".join(f'{65+910*i/max(1,maxlen-1):.2f},{420-370*v/ymax:.2f}' for i,v in enumerate(values))
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{palette[idx%len(palette)]}" stroke-width="1.8"/>')
        parts.append(f'<text x="{70+(idx%4)*230}" y="{447+(idx//4)*17}" font-family="sans-serif" font-size="12" fill="{palette[idx%len(palette)]}">{sat}</text>')
    parts.append(f'<text x="5" y="52" font-family="sans-serif" font-size="12">{ymax:.1f}</text>')
    parts.append('</svg>')
    path.write_text("\n".join(parts),encoding="utf-8")

def run(output_dir=None):
    out=Path(output_dir or ROOT/"outputs")
    out.mkdir(parents=True,exist_ok=True)
    baseline=plan(output_dir=out)
    sizing=trade_study(output_dir=out)
    hardware=compare(output_dir=out)
    antenna=evaluate(output_dir=out)
    mandatory=size_contacts(output_dir=out)
    history=_csv(out/"adaptive_storage_history.csv")
    _plot_history(history,out/"adaptive_memory_history.svg")
    rows=[]
    for sat,r in sorted(baseline["satellites"].items()):
        rows.append(f'| {sat} | {r["peak_memory_mbit"]:.2f} | {r["downlinked_mbit"]:.2f} | {r["remaining_mbit"]:.2f} | {r["contacts"]} | {", ".join(r["warnings"]) or "None"} |')
    report=[
        "# SELENA — preliminary OBDH/TT&C simulation",
        "",
        "**Status:** hypothetical, NOT an operational DSN allocation or verified 2030 orbital geometry.",
        "Historical 2020 geometric windows have been calendar-shifted to 2030 without orbital propagation.",
        "",
        f'**Scenario:** {baseline["scenario_start_utc"]} to {baseline["scenario_end_utc"]}.',
        f'**Net downlink:** {baseline["effective_downlink_bps"]/1000:.1f} kbps.',
        f'**DSN assigned:** {baseline["dsn_assigned_hours"]:.2f} shared hours.',
        f'**Contacts:** {baseline["contacts"]}.',
        "",
        "| Satellite | Peak memory (Mbit) | Downlinked (Mbit) | Remaining (Mbit) | Contacts | Violations |",
        "|---|---:|---:|---:|---:|---|",
        *rows,"",
        "## OBDH sizing",
        f'Minimum tested capacity avoiding storage violations: **{sizing["minimum_tested_storage_feasible_mbit"]} Mbit**.',
        f'Minimum tested capacity passing every modeled requirement: **{sizing["minimum_tested_all_constraints_pass_mbit"]} Mbit**.',
        "A null result means no tested option passed. This is not a continuous optimum or a flight memory selection.",
        "",
        "![Memory occupancy](adaptive_memory_history.svg)",
        "",
        "## Preliminary hardware trade",
        "See obdh_hardware_trade.csv and obdh_hardware_trade.json for documented candidate mass, power and dimensions.",
        "Candidates are not selected or qualified for lunar flight.",
        "",
        "## Antenna link budget",
        "See antenna_link_budget.csv and antenna_link_budget.json. Inputs pending.",
        "",
        "## Mandatory contact RF sizing",
        "See mandatory_link_sizing.csv and mandatory_link_sizing.json for required rates and RF input gaps.",
        "These are recurrence-volume estimates, not certified deadline-clearing results.",
        "",
        "## Limitations",
        "FIFO timestamps are discretized to five minutes. No actual DSN antenna reservations,",
        "HGA pointing/slew, power constraints, link-budget variation or stochastic packet loss are modeled.",
        "Rates, station availability, event bursts and deadlines are preliminary assumptions.",
        "The scheduler is a heuristic and may report infeasibility that a better scheduler could avoid.",
        "A finite 96-hour scenario does not prove long-term sustainable operations.",
        "",
        "## Files",
        "`adaptive_storage_summary.json`, `adaptive_storage_history.csv`,",
        "`adaptive_contact_schedule.csv`, `memory_sizing.csv`, `memory_sizing.json`.",
    ]
    (out/"SELENA_preliminary_report.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    return {"report":str(out/"SELENA_preliminary_report.md"),"sizing":sizing["minimum_tested_storage_feasible_mbit"],"contacts":baseline["contacts"]}

if __name__=="__main__":
    print(json.dumps(run(),indent=2))
