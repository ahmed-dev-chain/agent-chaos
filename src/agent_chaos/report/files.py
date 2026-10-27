"""JSON and static HTML reports."""
from __future__ import annotations

import html
import json
from pathlib import Path

from ..runner import RunSummary


def to_dict(summary: RunSummary) -> dict:
    lo, hi = summary.interval
    return {
        "score": round(summary.score, 2),
        "interval95": [round(lo, 2), round(hi, 2)],
        "gate_passed": summary.gate_passed,
        "unsafe": summary.unsafe_count,
        "scenarios": [
            {
                "name": r.scenario.name,
                "category": r.scenario.category,
                "trials": len(r.trials),
                "survived": sum(1 for t in r.trials if t.verdict.level.value == "survived"),
                "rate": round(r.rate, 4),
                "failures": [
                    {"trial": t.trial, "seed": t.seed, "verdict": t.verdict.to_dict(), "trace": t.trace}
                    for t in r.trials
                    if t.verdict.level.value in ("failed", "unsafe")
                ][:5],
            }
            for r in summary.results
        ],
    }


def write_json(summary: RunSummary, path: str | Path) -> None:
    Path(path).write_text(json.dumps(to_dict(summary), indent=2))


def write_html(summary: RunSummary, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    lo, hi = summary.interval
    rows = []
    for r in summary.results:
        bad = r.first_failure
        detail = ""
        if bad:
            trace = "\n".join(
                f"{e['id']:>2}. {e['name']}  faults={e['faults']}  error={e['error']}" for e in bad.trace
            )
            detail = (
                f"<details><summary>{html.escape(bad.verdict.reason)}</summary>"
                f"<pre>{html.escape(trace)}</pre></details>"
            )
        rows.append(
            f"<tr><td>{html.escape(r.scenario.name)}</td><td>{html.escape(r.scenario.category)}</td>"
            f"<td>{r.rate * 100:.0f}%</td><td>{detail}</td></tr>"
        )
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>agent-chaos report</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#14213d}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #d5dae3;padding:.5rem;text-align:left;vertical-align:top}}
.score{{font-size:3rem;font-weight:700}}.bad{{color:#e4572e}}.ok{{color:#17a398}}pre{{background:#0f172a;color:#e2e8f0;padding:.75rem;overflow:auto}}</style></head>
<body><h1>agent-chaos report</h1>
<div class="score {'ok' if summary.gate_passed else 'bad'}">{summary.score:.0f} / 100</div>
<p>95% CI {lo:.0f}-{hi:.0f} &middot; gate {'passed' if summary.gate_passed else 'FAILED'} &middot; unsafe outcomes: {summary.unsafe_count}</p>
<table><tr><th>Scenario</th><th>Category</th><th>Pass rate</th><th>First failure</th></tr>{''.join(rows)}</table></body></html>"""
    path = out / "index.html"
    path.write_text(page)
    return path
