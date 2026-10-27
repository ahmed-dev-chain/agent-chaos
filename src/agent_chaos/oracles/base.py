"""Oracles decide whether the agent survived. Built-ins are deterministic invariants."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..core.context import RunContext
from ..core.events import Level, Verdict

CheckFn = Callable[[RunContext, Any], "Verdict | None"]


class Oracle:
    """Wraps a check function. Return ``None`` for pass, or a :class:`Verdict` for a problem."""

    def __init__(self, name: str, fn: CheckFn):
        self.name = name
        self.fn = fn

    def __call__(self, ctx: RunContext, result: Any) -> Verdict | None:
        return self.fn(ctx, result)

    def __repr__(self) -> str:
        return f"Oracle({self.name})"


def max_steps(limit: int) -> Oracle:
    def check(ctx: RunContext, result: Any) -> Verdict | None:
        if len(ctx.events) > limit:
            return Verdict(Level.FAILED, f"{len(ctx.events)} calls exceeds limit of {limit}")
        return None

    return Oracle(f"max_steps({limit})", check)


def max_cost(limit: float) -> Oracle:
    def check(ctx: RunContext, result: Any) -> Verdict | None:
        if ctx.cost > limit:
            return Verdict(Level.DEGRADED, f"cost {ctx.cost:.4f} exceeds budget {limit:.4f}")
        return None

    return Oracle(f"max_cost({limit})", check)


def max_latency_ms(limit: float) -> Oracle:
    """Uses virtual time accumulated by injected delays."""

    def check(ctx: RunContext, result: Any) -> Verdict | None:
        if ctx.clock_ms > limit:
            return Verdict(Level.DEGRADED, f"virtual latency {ctx.clock_ms:.0f} ms exceeds {limit:.0f} ms")
        return None

    return Oracle(f"max_latency_ms({limit:.0f})", check)


def forbidden_action(tool: str, **arg_match: Any) -> Oracle:
    """UNSAFE if ``tool`` was executed with arguments matching ``arg_match`` (empty = any call)."""

    def check(ctx: RunContext, result: Any) -> Verdict | None:
        for e in ctx.events:
            if e.name == tool and e.executed and all(e.args.get(k) == v for k, v in arg_match.items()):
                return Verdict(Level.UNSAFE, f"forbidden action: {tool}({arg_match or '...'}) at step {e.id}")
        return None

    return Oracle(f"forbidden_action({tool})", check)


def no_duplicate_side_effect(*tools: str) -> Oracle:
    """UNSAFE if the same side effect executed more than once.

    Effects sharing an ``idempotency_key`` count as one (assumes the backend honors the key).
    Without a key, identical arguments count as the same effect.
    """

    def check(ctx: RunContext, result: Any) -> Verdict | None:
        unkeyed: dict[tuple[str, str], int] = {}
        for e in ctx.events:
            if not (e.executed and e.side_effect) or (tools and e.name not in tools):
                continue
            if e.idempotency_key:
                continue  # keyed effects are deduplicated by the backend
            ident = (e.name, repr(sorted((k, repr(v)) for k, v in e.args.items())))
            unkeyed[ident] = unkeyed.get(ident, 0) + 1
            if unkeyed[ident] > 1:
                return Verdict(
                    Level.UNSAFE,
                    f"duplicate side effect: {e.name} executed {unkeyed[ident]}x without an idempotency key",
                )
        return None

    return Oracle("no_duplicate_side_effect", check)


def result_check(predicate: Callable[[Any], bool], name: str = "result_check") -> Oracle:
    def check(ctx: RunContext, result: Any) -> Verdict | None:
        try:
            ok = bool(predicate(result))
        except Exception as exc:  # noqa: BLE001
            return Verdict(Level.FAILED, f"{name} raised {type(exc).__name__}: {exc}")
        return None if ok else Verdict(Level.FAILED, f"{name} failed: result={result!r}")

    return Oracle(name, check)
