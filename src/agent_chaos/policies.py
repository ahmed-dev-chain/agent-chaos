"""Policies decide *when* a fault fires. All randomness comes from the RunContext."""
from __future__ import annotations

from typing import Protocol

from .core.context import RunContext
from .core.events import Event


class Policy(Protocol):
    def should_fire(self, event: Event, ctx: RunContext) -> bool: ...


class Always:
    def should_fire(self, event: Event, ctx: RunContext) -> bool:
        return True


class Probability:
    """Fire with probability ``p`` on every matching event."""

    def __init__(self, p: float):
        if not 0.0 <= p <= 1.0:
            raise ValueError("p must be between 0 and 1")
        self.p = p

    def should_fire(self, event: Event, ctx: RunContext) -> bool:
        return ctx.rng.random() < self.p


class OnCall:
    """Fire only on the Nth call (1-based) of a given tool/endpoint."""

    def __init__(self, n: int):
        self.n = n

    def should_fire(self, event: Event, ctx: RunContext) -> bool:
        return event.index == self.n


class FirstN:
    """Fire on the first N calls, then stop. Good for testing retry logic."""

    def __init__(self, n: int):
        self.n = n

    def should_fire(self, event: Event, ctx: RunContext) -> bool:
        return event.index <= self.n
