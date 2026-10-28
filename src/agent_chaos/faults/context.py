"""Faults that strike the agent's context: window overflow, memory corruption.

These operate on the structured output of whatever call they are attached to (typically a
``model=`` or ``retrieval=`` wrapped call that returns conversation history or retrieved
context), rather than on a dedicated "context" event kind, so they need no changes to the core
event model to exist.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..core.context import RunContext
from ..core.events import Event
from ..policies import Policy
from .base import Fault, register_fault


@register_fault
class WindowOverflow(Fault):
    """The context window fills up: older entries fall out, only the most recent ``keep`` fraction survives."""

    name = "window_overflow"
    category = "context"

    def __init__(self, where: str | None = None, policy: Policy | None = None, keep: float = 0.5):
        super().__init__(where, policy)
        self.keep = keep

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        return _drop_front(call(), self.keep)


@register_fault
class MemoryCorruption(Fault):
    """An earlier entry in the result is silently altered, as if memory had been corrupted."""

    name = "memory_corruption"
    category = "context"

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        return _corrupt_one(call(), ctx)


def _drop_front(value: Any, keep: float) -> Any:
    if isinstance(value, dict):
        if not value:
            return value
        n = max(1, int(len(value) * keep))
        keys = list(value)[-n:]
        return {k: value[k] for k in keys}
    if isinstance(value, (list, tuple)):
        if not value:
            return list(value)
        n = max(1, int(len(value) * keep))
        return list(value)[-n:]
    if isinstance(value, str):
        if not value:
            return value
        n = max(1, int(len(value) * keep))
        return value[-n:]
    return value


def _corrupt_one(value: Any, ctx: RunContext) -> Any:
    if isinstance(value, list) and value:
        i = ctx.rng.randrange(len(value))
        out = list(value)
        out[i] = _mutate(out[i])
        return out
    if isinstance(value, dict) and value:
        k = ctx.rng.choice(list(value))
        out = dict(value)
        out[k] = _mutate(out[k])
        return out
    return value


def _mutate(item: Any) -> Any:
    if isinstance(item, str):
        return item[::-1]
    if isinstance(item, dict):
        return {k: None for k in item}
    return None
