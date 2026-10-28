"""Scenario runner: expands trials, applies faults, judges, scores."""
from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from .core.context import RunContext, _run_sync
from .core.errors import StepLimitExceeded
from .core.events import SEVERITY, Level, Verdict
from .faults.base import Fault
from .oracles.base import Oracle
from .scoring import pass_rate, wilson_interval

Target = Callable[[str, RunContext], Any]


@dataclass
class Scenario:
    name: str
    target: Target
    task: str
    faults: Sequence[Fault] = ()
    oracles: Sequence[Oracle] = ()
    trials: int = 20
    seed: int = 0
    category: str = "general"
    hard_step_cap: int = 100


@dataclass
class TrialResult:
    scenario: str
    trial: int
    seed: int
    verdict: Verdict
    trace: list[dict[str, Any]] = field(default_factory=list)
    result: Any = None


@dataclass
class ScenarioResult:
    scenario: Scenario
    trials: list[TrialResult]

    def count(self, level: Level) -> int:
        return sum(1 for t in self.trials if t.verdict.level == level)

    @property
    def rate(self) -> float:
        return pass_rate(self.count(Level.SURVIVED), self.count(Level.DEGRADED), len(self.trials))

    @property
    def first_failure(self) -> TrialResult | None:
        bad = [t for t in self.trials if t.verdict.level in (Level.FAILED, Level.UNSAFE)]
        return max(bad, key=lambda t: SEVERITY[t.verdict.level]) if bad else None


@dataclass
class RunSummary:
    results: list[ScenarioResult]
    min_score: float = 0.0
    block_on_unsafe: bool = True

    @property
    def total_trials(self) -> int:
        return sum(len(r.trials) for r in self.results)

    @property
    def score(self) -> float:
        total = self.total_trials
        if not total:
            return 0.0
        good = sum(r.count(Level.SURVIVED) + 0.5 * r.count(Level.DEGRADED) for r in self.results)
        return 100.0 * good / total

    @property
    def interval(self) -> tuple[float, float]:
        total = self.total_trials
        good = sum(r.count(Level.SURVIVED) + 0.5 * r.count(Level.DEGRADED) for r in self.results)
        lo, hi = wilson_interval(good, total)
        return 100 * lo, 100 * hi

    @property
    def unsafe_count(self) -> int:
        return sum(r.count(Level.UNSAFE) for r in self.results)

    @property
    def gate_passed(self) -> bool:
        if self.block_on_unsafe and self.unsafe_count:
            return False
        return self.score >= self.min_score


def trial_seed(base: int, trial: int) -> int:
    return base * 1_000_003 + trial


def run_trial(scenario: Scenario, trial: int) -> TrialResult:
    seed = trial_seed(scenario.seed, trial)
    ctx = RunContext(seed, scenario.faults, scenario.hard_step_cap)
    result: Any = None
    try:
        result = scenario.target(scenario.task, ctx)
        if inspect.isawaitable(result):  # the target is an async agent; drive it to completion
            result = _run_sync(result)
    except StepLimitExceeded as exc:
        verdict = Verdict(Level.FAILED, f"loop detected: {exc}")
    except Exception as exc:  # noqa: BLE001 - any crash is a failed trial
        verdict = Verdict(Level.FAILED, f"crashed: {type(exc).__name__}: {exc}")
    else:
        verdict = Verdict(Level.SURVIVED, "")
        for oracle in scenario.oracles:
            found = oracle(ctx, result)
            if found and SEVERITY[found.level] > SEVERITY[verdict.level]:
                verdict = found
    return TrialResult(scenario.name, trial, seed, verdict, ctx.trace(), result)


def run_scenario(scenario: Scenario, trials: int | None = None) -> ScenarioResult:
    n = trials if trials is not None else scenario.trials
    return ScenarioResult(scenario, [run_trial(scenario, i) for i in range(n)])


def run_all(
    scenarios: Sequence[Scenario],
    trials: int | None = None,
    seed: int | None = None,
    min_score: float = 0.0,
) -> RunSummary:
    results = []
    for sc in scenarios:
        if seed is not None:
            sc.seed = seed
        results.append(run_scenario(sc, trials))
    return RunSummary(results, min_score=min_score)
