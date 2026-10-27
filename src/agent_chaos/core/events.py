"""Normalized event model. Every interception strategy emits these."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Kind(str, Enum):
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    HTTP = "http"
    RETRIEVAL = "retrieval"
    MCP = "mcp"


class Level(str, Enum):
    """Verdict levels, ordered from best to worst by SEVERITY."""

    SURVIVED = "survived"
    DEGRADED = "degraded"
    FAILED = "failed"
    UNSAFE = "unsafe"


SEVERITY = {Level.SURVIVED: 0, Level.DEGRADED: 1, Level.FAILED: 2, Level.UNSAFE: 3}


@dataclass
class Verdict:
    level: Level
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"level": self.level.value, "reason": self.reason}


@dataclass
class Event:
    id: int
    kind: Kind
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    index: int = 1  # 1-based count of calls with this name in the trial
    side_effect: bool = False
    idempotency_key: str | None = None
    executed: bool = False  # did the real call actually run?
    response: Any = None
    error: str | None = None
    faults: list[str] = field(default_factory=list)
    virtual_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "name": self.name,
            "args": _safe(self.args),
            "index": self.index,
            "side_effect": self.side_effect,
            "idempotency_key": self.idempotency_key,
            "executed": self.executed,
            "response": _safe(self.response),
            "error": self.error,
            "faults": list(self.faults),
            "virtual_ms": self.virtual_ms,
        }


def _safe(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_safe(v) for v in value]
    return repr(value)
