"""pytest integration: ``chaos`` fixture."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from .runner import RunSummary, Scenario, run_all, run_scenario


def assert_resilient(summary_or_result, min_score: float = 90.0, allow_unsafe: bool = False) -> None:
    summary = (
        summary_or_result
        if isinstance(summary_or_result, RunSummary)
        else RunSummary([summary_or_result])
    )
    if summary.unsafe_count and not allow_unsafe:
        bad = next(r.first_failure for r in summary.results if r.first_failure)
        raise AssertionError(f"unsafe outcome: {bad.verdict.reason} (trial {bad.trial}, seed {bad.seed})")
    if summary.score < min_score:
        bad = next((r.first_failure for r in summary.results if r.first_failure), None)
        detail = f"; first failure: {bad.verdict.reason}" if bad else ""
        raise AssertionError(f"resilience score {summary.score:.0f} < {min_score:.0f}{detail}")


@pytest.fixture
def chaos() -> SimpleNamespace:
    """Usage::

        def test_agent(chaos):
            result = chaos.run(Scenario(...))
            chaos.assert_resilient(result, min_score=95)
    """
    return SimpleNamespace(
        Scenario=Scenario,
        run=run_scenario,
        run_all=run_all,
        assert_resilient=assert_resilient,
    )
