"""RunContext: the single source of randomness, time and recorded events for one trial."""
from __future__ import annotations

import asyncio
import inspect
import random
import threading
from collections.abc import Awaitable, Callable, Sequence
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
    def _new_event(
        self,
        kind: Kind,
        name: str,
        args: dict[str, Any] | None,
        side_effect: bool,
        idempotency_key: str | None,
    ) -> Event:
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
        return event

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
        event = self._new_event(kind, name, args, side_effect, idempotency_key)

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

    async def acall(
        self,
        kind: Kind,
        name: str,
        fn: Callable[[], Awaitable[Any]],
        *,
        args: dict[str, Any] | None = None,
        side_effect: bool = False,
        idempotency_key: str | None = None,
    ) -> Any:
        """Async counterpart of :meth:`call`, for awaitable targets (e.g. async httpx clients).

        Faults are plain sync code and are reused unchanged: when no fault actually intercepts
        the call, ``fn`` is awaited directly (fully concurrent, like any other coroutine). When a
        fault *does* intercept it (to corrupt the result, replay it twice, etc.), that fault's
        synchronous ``apply`` runs the real awaitable to completion on a worker thread via
        :func:`_run_sync` — correct, but that one call blocks its caller for its duration instead
        of yielding to the event loop, same as a sync call would.
        """
        event = self._new_event(kind, name, args, side_effect, idempotency_key)

        async def real() -> Any:
            event.executed = True
            return await fn()

        fired = [f for f in self.faults if f.matches(event) and f.policy.should_fire(event, self)]
        event.faults = [f.name for f in fired]
        try:
            if not fired:
                event.response = await real()
            else:
                call: Callable[[], Any] = lambda: _run_sync(real())  # noqa: E731
                for fault in reversed(fired):
                    call = _chain(fault, event, self, call)
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

    def awrap(
        self,
        name: str,
        fn: Callable[..., Awaitable[Any]],
        *,
        kind: Kind = Kind.TOOL_CALL,
        side_effect: bool = False,
    ) -> Callable[..., Awaitable[Any]]:
        """Async counterpart of :meth:`wrap`, for agent tools that are themselves coroutines."""
        sig = inspect.signature(fn)

        async def wrapped(*a: Any, **kw: Any) -> Any:
            try:
                bound = sig.bind(*a, **kw)
                call_args = dict(bound.arguments)
            except TypeError:
                call_args = dict(kw)
            return await self.acall(
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


def _run_sync(coro: Awaitable[Any]) -> Any:
    """Run ``coro`` to completion from sync code, even if called from inside a running loop."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # type: ignore[arg-type]

    box: dict[str, Any] = {}

    def runner() -> None:
        try:
            box["result"] = asyncio.run(coro)  # type: ignore[arg-type]
        except BaseException as exc:  # noqa: BLE001 - re-raised on the calling thread below
            box["error"] = exc

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["result"]
