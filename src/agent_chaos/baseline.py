"""File-based baselines: save a run's per-scenario pass rates, compare a later run against them.

No database, no external service -- a single committed JSON file, consistent with the project's
existing "zero setup, inspectable" storage philosophy (JSONL traces, SQLite-free).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .core.events import Level
from .runner import RunSummary

REGRESSION_THRESHOLD = 0.05  # a rate drop bigger than this (5 points) counts as a regression


@dataclass
class ScoreDiff:
    scenario: str
    baseline_rate: float | None
    current_rate: float
    regressed: bool


def save_baseline(summary: RunSummary, path: str | Path) -> None:
    data = {r.scenario.name: round(r.rate, 4) for r in summary.results}
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True))


def compare_baseline(summary: RunSummary, path: str | Path) -> list[ScoreDiff]:
    p = Path(path)
    baseline: dict[str, float] = json.loads(p.read_text()) if p.exists() else {}
    diffs = []
    for r in summary.results:
        base = baseline.get(r.scenario.name)
        regressed = bool(r.count(Level.UNSAFE)) or (base is not None and r.rate < base - REGRESSION_THRESHOLD)
        diffs.append(ScoreDiff(r.scenario.name, base, round(r.rate, 4), regressed))
    return diffs
