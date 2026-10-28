"""Faults that strike tool and API calls."""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

from ..core.context import RunContext
from ..core.errors import ToolError, ToolTimeout
from ..core.events import Event
from ..policies import Policy
from .base import Fault, register_fault


@register_fault
class Timeout(Fault):
    """The tool never answers. The real call is NOT executed."""

    name = "timeout"

    def __init__(self, where: str | None = None, policy: Policy | None = None, ms: float = 30_000):
        super().__init__(where, policy)
        self.ms = ms

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        event.virtual_ms += self.ms
        raise ToolTimeout(f"{event.name} timed out after {self.ms:.0f} ms (simulated)")


@register_fault
class ErrorStatus(Fault):
    """The tool answers with an error status (500, 429, 401, ...). The real call is NOT executed."""

    name = "error_status"

    def __init__(self, where: str | None = None, policy: Policy | None = None, status: int = 500):
        super().__init__(where, policy)
        self.status = status

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        raise ToolError(self.status, f"{event.name} returned {self.status} (injected)")


@register_fault
class RateLimit(ErrorStatus):
    """Shortcut for HTTP 429."""

    name = "rate_limit"

    def __init__(self, where: str | None = None, policy: Policy | None = None):
        super().__init__(where, policy, status=429)


@register_fault
class MalformedOutput(Fault):
    """The call succeeds but the payload is corrupted: truncated or with nulled values."""

    name = "malformed_output"

    def __init__(self, where: str | None = None, policy: Policy | None = None, mode: str = "truncate"):
        super().__init__(where, policy)
        if mode not in {"truncate", "null_values"}:
            raise ValueError("mode must be 'truncate' or 'null_values'")
        self.mode = mode

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        return _corrupt(call(), self.mode)


def _corrupt(value: Any, mode: str, keep: float = 0.5) -> Any:
    # httpx.Response-like objects
    if hasattr(value, "status_code") and hasattr(value, "content"):
        try:
            cut = int(len(value.content) * keep)
            return type(value)(value.status_code, content=value.content[:cut], request=value.request)
        except Exception:  # noqa: BLE001
            return value
    if isinstance(value, dict):
        if mode == "null_values":
            return {k: None for k in value}
        keys = list(value)[: max(1, int(len(value) * keep))]
        return {k: value[k] for k in keys}
    if isinstance(value, (list, tuple)):
        return list(value)[: max(1, int(len(value) * keep))] if value else []
    if isinstance(value, str):
        return value[: max(1, int(len(value) * keep))] if value else value
    return None if mode == "null_values" else value


@register_fault
class PartialSuccess(Fault):
    """The side effect HAPPENS but the response is lost. Exposes unsafe retries."""

    name = "partial_success"

    def __init__(self, where: str | None = None, policy: Policy | None = None, ms: float = 30_000):
        super().__init__(where, policy)
        self.ms = ms

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        call()  # real effect occurs
        event.virtual_ms += self.ms
        raise ToolTimeout(f"{event.name} response lost after the action succeeded (simulated)")


@register_fault
class DuplicateDelivery(Fault):
    """The call is delivered twice (at-least-once delivery)."""

    name = "duplicate_delivery"

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        call()
        return call()


@register_fault
class StaleData(Fault):
    """Returns a fixed outdated value instead of the real response."""

    name = "stale_data"

    def __init__(self, where: str | None = None, policy: Policy | None = None, value: Any = None):
        super().__init__(where, policy)
        self.value = value

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        call()
        return copy.deepcopy(self.value)
