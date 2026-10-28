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
| Oracles (invariants, trajectory, pluggable LLM-judge) | `oracles/base.py`, `oracles/trajectory.py`, `oracles/judge.py` |
| Scenario runner and gate | `runner.py` |
| Resilience score and Wilson interval | `scoring.py` |
| Terminal, JSON, HTML, SARIF and JUnit XML reports | `report/` |
| SDK-level interception (httpx, sync and async) | `intercept/httpx_patch.py` |
| Shared tool wrapping (`func`/`coroutine` and `_run`/`_arun`) | `adapters/tools.py` |
| LangGraph adapter (node wrapping) | `adapters/langgraph.py` |
| OpenAI Agents SDK adapter (`FunctionTool.on_invoke_tool`) | `adapters/openai_agents.py` |
| CrewAI adapter | `adapters/crewai.py` |
| `chaos init` framework detection and scenario scaffold | `scaffold.py` |
| Record and replay (`ReplayFault`, `save_trace`, `load_replay`) | `record.py` |
| Failure shrinking (`shrink`) | `shrink.py` |
| File-based baselines (`save_baseline`, `compare_baseline`) | `baseline.py` |
| CLI (`run`, `replay`, `record`, `shrink`, `faults`, `init`) and pytest fixture | `cli.py`, `pytest_plugin.py` |

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

Transparent proxy mode, trend tracking over time, sweeps, the public benchmark write-up, and
publishing the docs site. See `ROADMAP.md` and the blueprint PDF.

## Known limits of v0.1 / v0.2

- `no_duplicate_side_effect` trusts that a backend honors an `idempotency_key`.
- `RunContext.acall` reuses the existing synchronous `Fault.apply` methods unchanged (so every
  fault works against async targets for free, with zero per-fault async code). The cost: an
  unfaulted async call stays fully concurrent (awaited directly), but once a fault actually
  intercepts a call, that one call runs to completion on a worker thread via `core.context._run_sync`
  rather than yielding to the event loop — correct, but not concurrency-preserving, for that call.
  A fully async-native fault pipeline (`async def apply`) is a bigger step, not taken yet.
- Faults are applied per call; storylines and fault composition arrive in v1.0.
- Every `adapters/` module is duck-typed: no hard dependency, optional or otherwise, on
  `langgraph`/`langchain-core`/`crewai`/`agents`. `adapters/tools.py`'s `wrap_tool` covers both
  shapes a tool library actually uses — `func`/`coroutine` (LangChain's decorator-built tools) and
  `_run`/`_arun` (any custom `BaseTool` subclass, including CrewAI's) — so `adapters/langgraph.py`
  and `adapters/crewai.py` both just re-export it; only `wrap_node` (LangGraph) and
  `wrap_function_tool`/`wrap_function_tools` (`adapters/openai_agents.py`, wrapping
  `FunctionTool.on_invoke_tool`) are framework-specific.
- `record.py`'s `ReplayFault` matches recordings by `(kind, name, index)`, not call position, so
  it replays identically across any number of trials in the same `Scenario`. A recording that
  originally errored can't round-trip its exact exception type through `Event.to_dict()`'s
  string-only `error` field, so replaying it raises a generic `ReplayedError` carrying that
  string. Replay assumes the target's call *sequence* is otherwise deterministic given the same
  task/inputs (branching purely on a tool's return value won't replay correctly if that tool's
  call count differs from the recording) -- it raises `ReplayMismatch` rather than silently
  guessing when that assumption breaks.
- `shrink.py`'s `shrink` re-verifies every candidate fault subset by actually rerunning the trial,
  so its result is always a genuine reproduction. It isn't guaranteed globally minimal, because
  `Policy.should_fire` draws from `ctx.rng` for every fault in the list on every event (not just
  the ones that end up firing), so removing one fault shifts the draws the rest consume.
- `baseline.py` has no history: `save_baseline` always overwrites the one baseline file with the
  latest run, and `compare_baseline` only sees that single snapshot. A regression is "unsafe now
  when it wasn't in the baseline" or "pass rate dropped more than 5 points" -- there's no trend
  over multiple runs yet.
- `oracles/judge.py`'s `llm_judge` makes no LLM call itself -- `judge_fn(ctx, result) -> float` is
  entirely the caller's. There's no built-in position-bias control or prompt template; `calibrate`
  only reports an agreement rate against a hand-labeled set, which the caller still has to build.
