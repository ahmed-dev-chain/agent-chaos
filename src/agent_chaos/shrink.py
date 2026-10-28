"""Failure shrinking: reduce a failing scenario's fault list to the smallest set that still
reproduces the failure. Built entirely on runner.run_trial -- zero core changes.
"""
from __future__ import annotations

from dataclasses import replace

from .core.events import SEVERITY, Level
from .runner import Scenario, run_trial


def shrink(scenario: Scenario, trial: int, min_severity: Level = Level.FAILED) -> Scenario:
    """Smallest subset of ``scenario.faults`` (same trial/seed) that still reproduces a verdict
    at least as severe as ``min_severity``.

    Every candidate subset is actually re-run and checked, so the result is always a genuine
    reproduction, never a guess. It isn't guaranteed to be the theoretical global minimum, though:
    ``Policy.should_fire`` draws from ``ctx.rng`` for *every* fault in the list on every event, not
    just the ones that end up firing, so dropping one fault shifts the random draws the remaining
    faults consume and can change which of them fire. Shrinking stays correct under that -- it only
    ever accepts a smaller list once rerunning it actually reproduces the target severity -- it
    just isn't guaranteed optimal.
    """
    target = SEVERITY[min_severity]

    def reproduces(subset: list) -> bool:
        candidate = replace(scenario, faults=subset)
        result = run_trial(candidate, trial)
        return SEVERITY[result.verdict.level] >= target

    faults = list(scenario.faults)
    if not reproduces(faults):
        raise ValueError(
            f"{scenario.name!r} trial {trial} doesn't reproduce a verdict >= {min_severity.value!r}"
        )

    changed = True
    while changed:
        changed = False
        for f in list(faults):
            candidate = [x for x in faults if x is not f]
            if reproduces(candidate):
                faults = candidate
                changed = True
                break

    return replace(scenario, faults=faults)
