"""Trajectory oracles: invariants over the *sequence* of calls, not just individual outcomes."""
from __future__ import annotations

from typing import Any

from ..core.context import RunContext
from ..core.events import Level, Verdict
from .base import Oracle


def tool_order(*names: str) -> Oracle:
    """FAILED unless the named tools' first executed calls happen in this relative order."""

    def check(ctx: RunContext, result: Any) -> Verdict | None:
        first: dict[str, int] = {}
        for e in ctx.events:
            if e.executed and e.name in names and e.name not in first:
                first[e.name] = e.id
        missing = [n for n in names if n not in first]
        if missing:
            return Verdict(Level.FAILED, f"tool_order: {missing[0]!r} was never called")
        ids = [first[n] for n in names]
        if ids != sorted(ids):
            return Verdict(Level.FAILED, f"tool_order: expected {list(names)} in order, got call ids {ids}")
        return None

    return Oracle(f"tool_order({','.join(names)})", check)


def max_retries(tool: str, limit: int) -> Oracle:
    """FAILED if ``tool`` was called more than ``limit`` times in a single trial."""

    def check(ctx: RunContext, result: Any) -> Verdict | None:
        worst = max((e.index for e in ctx.events if e.name == tool), default=0)
        if worst > limit:
            return Verdict(Level.FAILED, f"{tool} called {worst}x, exceeds retry limit {limit}")
        return None

    return Oracle(f"max_retries({tool},{limit})", check)


def no_call_loop(limit: int = 3) -> Oracle:
    """FAILED if the same call (name + args) repeats more than ``limit`` times back to back.

    Tighter and earlier than ``max_steps``'s blunt total-call cap: this catches a stuck retry loop
    on one call while the overall trial is still well under the step limit.
    """

    def check(ctx: RunContext, result: Any) -> Verdict | None:
        prev: tuple[str, str] | None = None
        streak = 0
        for e in ctx.events:
            ident = (e.name, repr(sorted((k, repr(v)) for k, v in e.args.items())))
            streak = streak + 1 if ident == prev else 1
            prev = ident
            if streak > limit:
                return Verdict(Level.FAILED, f"loop detected: {e.name} repeated {streak}x consecutively")
        return None

    return Oracle(f"no_call_loop({limit})", check)
