"""Record and replay: capture one real, unfaulted run's trace, then replay it offline for free.

Built entirely on the existing Fault/RunContext contract -- zero core changes. ``ReplayFault`` is
a normal fault with ``where=None`` (matches every call) and ``policy=Always()``: instead of ever
invoking the real call, it hands back the next recorded response in sequence. A ``Scenario`` whose
only fault is a loaded replay runs with no network, no model cost, and the exact same result every
time, regardless of seed.

    ctx = RunContext(0, [])
    result = my_agent(task, ctx)          # one real, unfaulted run
    save_trace(ctx, "trace.json")

    replay_scenario = Scenario(
        name="replay", target=my_agent, task=task,
        faults=[load_replay("trace.json")], oracles=[...],
    )
"""
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .core.context import RunContext
from .core.errors import ReplayedError, ReplayMismatch
from .core.events import Event
from .faults.base import Fault, register_fault
from .policies import Always


def save_trace(ctx: RunContext, path: str | Path) -> None:
    """Write ``ctx``'s recorded trace (every call, in order, with its real response) to ``path``."""
    Path(path).write_text(json.dumps(ctx.trace(), indent=2))


@register_fault
class ReplayFault(Fault):
    """Replays a previously recorded trace instead of running the real calls.

    Matches recordings by ``(kind, name, index)`` -- the call's own kind, name and 1-based
    per-trial call count -- rather than draining a queue, so the same recording replays
    identically across any number of trials, not just once.
    """

    name = "replay"
    category = "replay"

    def __init__(self, recorded: list[dict[str, Any]]):
        super().__init__(where=None, policy=Always())
        self._by_key: dict[tuple[str, str, int], dict[str, Any]] = {
            (r["kind"], r["name"], r["index"]): r for r in recorded
        }

    def apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any:
        rec = self._by_key.get((event.kind.value, event.name, event.index))
        if rec is None:
            raise ReplayMismatch(
                f"no recording for {event.kind.value}/{event.name!r} call #{event.index} "
                "-- the target's call sequence has diverged from the recording"
            )
        if rec["error"]:
            raise ReplayedError(rec["error"])
        return rec["response"]


def load_replay(path: str | Path) -> ReplayFault:
    """Build a :class:`ReplayFault` from a trace file written by :func:`save_trace`."""
    return ReplayFault(json.loads(Path(path).read_text()))
