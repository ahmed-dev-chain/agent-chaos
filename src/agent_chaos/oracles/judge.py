"""Pluggable LLM-judge oracle. agent-chaos makes no LLM call of its own: you supply judge_fn.

Deterministic oracles (``oracles/base.py``, ``oracles/trajectory.py``) are always preferable where
they can express the check -- this exists for genuinely open-ended "is this answer any good"
checks that need a judge. Keeping it pluggable rather than baking in a provider keeps agent-chaos
at zero runtime dependencies and lets the caller use whatever model/SDK they already have.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from ..core.context import RunContext
from ..core.events import Level, Verdict
from .base import Oracle

JudgeFn = Callable[[RunContext, Any], float]


def llm_judge(name: str, judge_fn: JudgeFn, *, threshold: float = 0.7) -> Oracle:
    """DEGRADED if ``judge_fn(ctx, result)`` scores below ``threshold``.

    ``judge_fn`` is entirely the caller's: make your own call to whatever model/provider you want,
    and close over the task/prompt it needs to judge against. Must return a score in ``[0, 1]``.
    """

    def check(ctx: RunContext, result: Any) -> Verdict | None:
        score = judge_fn(ctx, result)
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"judge_fn must return a score in [0, 1], got {score!r}")
        if score < threshold:
            return Verdict(Level.DEGRADED, f"llm_judge score {score:.2f} below threshold {threshold}")
        return None

    return Oracle(name, check)


def calibrate(judge_fn: JudgeFn, labeled: Sequence[tuple[RunContext, Any, bool]]) -> float:
    """Agreement rate of ``judge_fn`` against a hand-labeled calibration set.

    Each item in ``labeled`` is ``(ctx, result, expected_pass)``. Returns the fraction where
    ``(judge_fn(ctx, result) >= 0.5) == expected_pass`` -- run this once against a small labeled
    set before trusting a judge in CI, per the "judge reliability" guidance in the blueprint.
    """
    if not labeled:
        return 0.0
    agree = sum(1 for ctx, result, expected in labeled if (judge_fn(ctx, result) >= 0.5) == expected)
    return agree / len(labeled)
