"""RunContext: the single source of randomness, time and recorded events for one trial."""
from __future__ import annotations

import inspect
import random
from collections.abc import Callable, Sequence
from typing import Any

from .errors import StepLimitExceeded
from .events import Event, Kind


class RunContext:
    """Holds per-trial state. All randomness comes from ``self.rng`` so a seed replays exactly."""

    def __init__(self, seed: int, faults: Sequence[Any] = (), hard_step_cap: int = 100):
        self.seed = seed
        self.rng = random.Random(seed)
        self.faults = list(faults)
        self.hard_step_cap = hard_step_cap
        self.events: list[Event] = []
        self.clock_ms: float = 0.0
        self.cost: float = 0.0
        self._counts: dict[tuple[str, str], int] = {}

    # ---- interception entry point -------------------------------------------------
    def call(
        self,
        kind: Kind,
        name: str,
        fn: Callable[[], Any],
        *,
        args: dict[str, Any] | None = None,
        side_effect: bool = False,
        idempotency_key: str | None = None,
    ) -> Any:
        """Run ``fn`` through the fault engine and record the event."""
        if len(self.events) >= self.hard_step_cap:
            raise StepLimitExceeded(f"more than {self.hard_step_cap} calls; likely an infinite loop")
        key = (kind.value, name)
        self._counts[key] = self._counts.get(key, 0) + 1
        event = Event(
            id=len(self.events) + 1,
            kind=kind,
            name=name,
            args=dict(args or {}),
            index=self._counts[key],
            side_effect=side_effect,
            idempotency_key=idempotency_key,
        )
        self.events.append(event)

        def real() -> Any:
            event.executed = True
            return fn()

        fired = [f for f in self.faults if f.matches(event) and f.policy.should_fire(event, self)]
        call: Callable[[], Any] = real
        for fault in reversed(fired):
            call = _chain(fault, event, self, call)
        event.faults = [f.name for f in fired]
        try:
            event.response = call()
            return event.response
        except Exception as exc:  # noqa: BLE001 - we record then re-raise
            event.error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            self.clock_ms += event.virtual_ms

    # ---- convenience for agent authors -------------------------------------------
    def wrap(
        self,
        name: str,
        fn: Callable[..., Any],
        *,
        kind: Kind = Kind.TOOL_CALL,
        side_effect: bool = False,
    ) -> Callable[..., Any]:
        """Return ``fn`` wrapped so every call goes through the fault engine."""
        sig = inspect.signature(fn)

        def wrapped(*a: Any, **kw: Any) -> Any:
            try:
                bound = sig.bind(*a, **kw)
                call_args = dict(bound.arguments)
            except TypeError:
                call_args = dict(kw)
            return self.call(
                kind,
                name,
                lambda: fn(*a, **kw),
                args=call_args,
                side_effect=side_effect,
                idempotency_key=call_args.get("idempotency_key"),
            )

        wrapped.__name__ = name
        return wrapped

    def add_cost(self, amount: float) -> None:
        self.cost += amount

    def trace(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self.events]


def _chain(fault: Any, event: Event, ctx: RunContext, inner: Callable[[], Any]) -> Callable[[], Any]:
    return lambda: fault.apply(event, ctx, inner)
