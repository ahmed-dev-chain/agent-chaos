"""Faults that strike model calls: refusal, format drift, truncation."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..core.context import RunContext
from ..core.events import Event
from ..policies import Policy
from .base import Fault, register_fault
from .tool import _corrupt

DEFAULT_REFUSAL = "I'm sorry, I can't help with that request."


@register_fault
class Refusal(Fault):
    """The model refuses to answer instead of completing the task. The real call is NOT executed."""

    name = "refusal"
    category = "model"

    def __init__(self, where: str | None = None, policy: Policy | None = None, message: str = DEFAULT_REFUSAL):
        super().__init__(where, policy)
        self.message = message

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        return self.message


@register_fault
class FormatDrift(Fault):
    """The model ignores the requested schema or language, flattening structured output to loose text."""

    name = "format_drift"
    category = "model"

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        return _drift(call())


@register_fault
class Truncation(Fault):
    """The model's output is cut off at the token limit, leaving a half-finished result."""

    name = "truncation"
    category = "model"

    def __init__(self, where: str | None = None, policy: Policy | None = None, keep: float = 0.5):
        super().__init__(where, policy)
        self.keep = keep

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        return _corrupt(call(), "truncate", self.keep)


def _drift(value: Any) -> Any:
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return "; ".join(str(v) for v in value)
    if isinstance(value, str):
        return f"```\n{value}\n```"
    return value
