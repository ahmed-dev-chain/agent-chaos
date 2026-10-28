# Architecture

Five layers, top to bottom: **interfaces** (CLI, pytest plugin, Python API) -> **orchestration** (runner, seeds, budgets) -> **engines** (faults, oracles, trace, reports) -> **interception** (how events are captured) -> **system under test**.

## Implemented in v0.1

| Piece | Module |
| --- | --- |
| Normalized event model | `core/events.py` |
| Per-trial context: seeded RNG, virtual clock, step cap, event recording | `core/context.py` |
| Fault base class, `where` selectors, plugin loading via entry points | `faults/base.py` |
| Tool, model, context and security faults | `faults/tool.py`, `faults/model.py`, `faults/context.py`, `faults/security.py` |
| Policies | `policies.py` |
| Oracles | `oracles/base.py` |
| Scenario runner and gate | `runner.py` |
| Resilience score and Wilson interval | `scoring.py` |
| Terminal, JSON and HTML reports | `report/` |
| SDK-level interception (httpx, sync and async) | `intercept/httpx_patch.py` |
| CLI (`run`, `replay`, `faults`) and pytest fixture | `cli.py`, `pytest_plugin.py` |

## Control flow of one trial

1. `run_trial` builds a `RunContext(seed, faults)`.
2. The target calls `ctx.wrap(...)`-ed tools (or HTTP goes through `patch_httpx`). An async target
   (or an `ctx.awrap`-ed async tool) goes through `RunContext.acall` instead of `call`; `run_trial`
   detects an awaitable result and drives it to completion.
3. Each call becomes an `Event`. Every fault whose `where` matches and whose policy fires wraps the real call (outermost first).
4. Faults may short-circuit (timeout, error), corrupt the result (malformed, injection), or run the real call and then fail (partial success).
5. After the target returns, oracles inspect the trace and result. The worst verdict wins.
6. Verdicts roll up into the score, interval and gate.

## Extension points (stable contract)

`Fault.apply`, `Policy.should_fire`, `Oracle.__call__`, reporters, and (next) adapters. Third-party fault packs register under the `agent_chaos.faults` entry point.

## Not built yet

Transparent proxy mode, record and replay, LangGraph/LangChain adapters, trajectory and LLM-judge oracles, GitHub Action wrapper, sweeps. See `ROADMAP.md` and the blueprint PDF.

## Known limits of v0.1 / v0.2

- `no_duplicate_side_effect` trusts that a backend honors an `idempotency_key`.
- `RunContext.acall` reuses the existing synchronous `Fault.apply` methods unchanged (so every
  fault works against async targets for free, with zero per-fault async code). The cost: an
  unfaulted async call stays fully concurrent (awaited directly), but once a fault actually
  intercepts a call, that one call runs to completion on a worker thread via `core.context._run_sync`
  rather than yielding to the event loop — correct, but not concurrency-preserving, for that call.
  A fully async-native fault pipeline (`async def apply`) is a bigger step, not taken yet.
- Faults are applied per call; storylines and fault composition arrive in v1.0.
