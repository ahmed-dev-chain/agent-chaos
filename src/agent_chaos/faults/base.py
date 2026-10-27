"""Fault base class and plugin registry."""
from __future__ import annotations

from collections.abc import Callable
from fnmatch import fnmatchcase
from typing import Any

from ..core.context import RunContext
from ..core.events import Event, Kind
from ..policies import Always, Policy

FAULTS: dict[str, type[Fault]] = {}

_WHERE_KEYS = {
    "tool": Kind.TOOL_CALL,
    "model": Kind.MODEL_CALL,
    "http": Kind.HTTP,
    "mcp": Kind.MCP,
    "retrieval": Kind.RETRIEVAL,
}


def register_fault(cls: type[Fault]) -> type[Fault]:
    FAULTS[cls.name] = cls
    return cls


def load_plugins() -> None:
    """Load third-party fault packs registered under the ``agent_chaos.faults`` entry point."""
    from importlib.metadata import entry_points

    for ep in entry_points(group="agent_chaos.faults"):
        try:
            ep.load()
        except Exception:  # noqa: BLE001 - a broken plugin must not break the core
            continue


class Fault:
    """A single deliberate disturbance.

    ``where`` selects events, e.g. ``"tool=issue_refund"``, ``"http=api.stripe.*"`` or ``None`` for all.
    ``policy`` decides when it fires (default: always).
    Subclasses implement :meth:`apply`, which receives ``call`` (the real or next-fault call).
    """

    name = "fault"
    category = "tool"

    def __init__(self, where: str | None = None, policy: Policy | None = None):
        self.where = where
        self.policy: Policy = policy or Always()

    def matches(self, event: Event) -> bool:
        if not self.where or self.where == "*":
            return True
        key, _, pattern = self.where.partition("=")
        kind = _WHERE_KEYS.get(key)
        if kind is None or not pattern:
            raise ValueError(f"bad where={self.where!r}; use e.g. 'tool=name' or 'http=host*'")
        return event.kind == kind and fnmatchcase(event.name, pattern)

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(where={self.where!r}, policy={type(self.policy).__name__})"
