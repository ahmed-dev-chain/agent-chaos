from __future__ import annotations

from ..baseline import ScoreDiff
from ..core.events import Level
from ..runner import RunSummary


def render(summary: RunSummary, target_spec: str = "") -> str:
    lines = []
    width = 78
    lines.append(f"agent-chaos   trials={summary.total_trials}")
    lines.append("-" * width)
    for r in summary.results:
        n = len(r.trials)
        ok = r.count(Level.SURVIVED)
        if r.count(Level.UNSAFE):
            tag = "UNSAFE"
        elif r.count(Level.FAILED):
            tag = "FAIL"
        elif r.count(Level.DEGRADED):
            tag = "WARN"
        else:
            tag = "OK"
        lines.append(f"{r.scenario.name:<26} {ok:>3}/{n:<3} survived   {tag:<7}")
        bad = r.first_failure
        if bad:
            lines.append(f"    first failure: {bad.verdict.reason}")
            lines.append(f"    reproduce:     chaos replay {target_spec or '<target>'} --scenario {r.scenario.name} --trial {bad.trial}")
    lo, hi = summary.interval
    lines.append("-" * width)
    gate = "PASSED" if summary.gate_passed else "FAILED"
    extra = f" ({summary.unsafe_count} unsafe)" if summary.unsafe_count else ""
    lines.append(f"Resilience score: {summary.score:.0f} / 100  (95% CI {lo:.0f}-{hi:.0f})   Gate: {gate}{extra}")
    return "\n".join(lines)


def render_baseline_diff(diffs: list[ScoreDiff]) -> str:
    lines = ["baseline diff:"]
    for d in diffs:
        base = f"{d.baseline_rate * 100:.0f}%" if d.baseline_rate is not None else "new"
        tag = "REGRESSED" if d.regressed else "ok"
        lines.append(f"  {d.scenario:<26} {base:>5} -> {d.current_rate * 100:.0f}%   {tag}")
    return "\n".join(lines)
