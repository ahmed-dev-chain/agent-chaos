# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**agent-chaos** is chaos engineering for AI agents: it deliberately injects faults (timeouts, malformed
output, partial success, prompt injection, etc.) into an agent's tool/HTTP calls, then judges the agent's
behavior with oracles to produce a resilience score and a pass/fail CI gate. Pure Python, zero runtime
dependencies, Apache-2.0.

## Commands

```bash
pip install -e ".[dev]"             # install package + dev deps (pytest, httpx, ruff, mypy)
ruff check src tests examples       # lint
pytest                               # run all tests
pytest tests/test_core.py::test_name  # run a single test
chaos run examples/support_agent.py:NAIVE      # run a scenario file (fragile agent, expect failures)
chaos run examples/support_agent.py:HARDENED   # run the hardened agent (expect pass)
chaos replay examples/support_agent.py:NAIVE --scenario <name> --trial <n>  # reproduce one exact trial
chaos faults                        # list all registered faults
chaos init                          # detect the framework, write a starter chaos_scenarios.py

# optional, needs real API keys (copy .env.example -> .env) — not part of the test suite:
pip install -e ".[real-sdk]" && python examples/real_sdk_check.py
```

CI (`.github/workflows/ci.yml`) runs ruff, pytest, then gates on
`chaos run examples/support_agent.py:HARDENED --min-score 95` across Python 3.10–3.13.

## Architecture

Five layers (see `docs/ARCHITECTURE.md` for the authoritative version):

**interfaces** (`cli.py`, `pytest_plugin.py`, Python API) → **orchestration** (`runner.py`: expands a
`Scenario` into seeded trials) → **engines** (`faults/`, `oracles/`, `scoring.py`, `report/`) →
**interception** (`core/context.py`'s `RunContext.call`/`.wrap` and async `.acall`/`.awrap`,
`intercept/httpx_patch.py`) → **system under test** (the agent code being tested, e.g.
`examples/support_agent.py`).

### Control flow of one trial (`runner.run_trial`)

1. A deterministic `seed = trial_seed(scenario.seed, trial)` builds a fresh `RunContext(seed, faults)`.
   All randomness in a trial must go through `ctx.rng` — this is what makes failures exactly replayable
   via `chaos replay`.
2. The target agent function (signature `(task: str, ctx: RunContext) -> Any`, sync or async) calls tools
   wrapped with `ctx.wrap`/`ctx.awrap(name, fn, side_effect=..., kind=...)`, or makes HTTP calls through
   `patch_httpx(ctx)` (patches both `httpx.Client` and `httpx.AsyncClient`). `run_trial` awaits the target
   automatically if it returns a coroutine.
3. Every wrapped call becomes an `Event` (`core/events.py`) recorded on `ctx.events`. Faults whose `where`
   selector matches the event and whose `policy.should_fire()` returns true are chained around the real
   call, outermost-fault-first (`RunContext.call`, or `.acall` for async, in `core/context.py`). `acall`
   reuses every `Fault.apply` unchanged: an unfaulted async call stays fully concurrent, but once a fault
   actually intercepts one, that call is driven to completion on a worker thread (`core.context._run_sync`)
   instead of yielding to the event loop — correct, just not concurrency-preserving for that one call.
4. A `Fault.apply(event, ctx, call)` can short-circuit (raise instead of calling `call()`), corrupt the
   result (call `call()` then mutate it), or let the real effect happen and then fail the response
   (`PartialSuccess`) — this is what exposes unsafe-retry bugs.
5. After the target returns (or raises/hits `hard_step_cap`), each `Oracle` in `scenario.oracles` inspects
   `ctx` and the result; the most severe `Verdict` wins. Severity order: `survived` < `degraded` < `failed`
   < `unsafe` (`core/events.SEVERITY`).
6. `RunSummary` rolls verdicts into a 0–100 score (survived=1, degraded=0.5) with a Wilson confidence
   interval (`scoring.py`), and `gate_passed` fails if any trial was `unsafe` or the score is below
   `min_score`.

### Key extension points

- **New fault**: subclass `Fault` in `faults/tool.py`, `faults/model.py`, `faults/context.py` or
  `faults/security.py` (or a new module), implement `apply(event, ctx, call)`, decorate with
  `@register_fault`. `where` selectors use `"<kind>=<fnmatch pattern>"` (kinds: `tool`, `model`, `http`,
  `mcp`, `retrieval`); `policy` (from `policies.py`: `Always`, `Probability(p)`, `OnCall(n)`, `FirstN(n)`)
  decides *when* it fires. Note `faults/context.py`'s faults (`window_overflow`, `memory_corruption`) act
  on the structured output of whatever call they're attached to rather than a dedicated context event
  kind — there isn't one yet. Third-party fault packs register under the `agent_chaos.faults` entry point
  (loaded via `faults.base.load_plugins`).
- **New oracle**: add a function in `oracles/base.py` returning an `Oracle(name, check_fn)`, where
  `check_fn(ctx, result) -> Verdict | None`.
- **New reporter**: add to `report/` (terminal/JSON/HTML exist; follow the `render`/`write_html`/
  `write_json` pattern used by `cli.py`).
- **New framework adapter**: `adapters/tools.py` already covers any tool shaped like LangChain's
  (`func`/`coroutine`) or like a custom `BaseTool` (`_run`/`_arun`, e.g. CrewAI) — reuse
  `wrap_tool`/`wrap_tools` from there rather than re-implementing tool wrapping. Only add a new
  module (see `adapters/langgraph.py`'s `wrap_node`, `adapters/openai_agents.py`'s
  `wrap_function_tool`) when the framework's own invocation entrypoint is genuinely different
  (`FunctionTool.on_invoke_tool`, a graph node callable, ...). Duck-typed, no hard dependency on
  the target framework. If it adds a new detectable framework, also add a template to
  `scaffold.py`'s `_BODIES` and wire the module name into `detect_framework`'s `_FRAMEWORK_SPECS`
  (or a fingerprint check like `_has_openai_agents_sdk` if the module name is too generic to trust
  on `find_spec` alone).

### Known v0.1/v0.2 limits (don't assume otherwise)

- `no_duplicate_side_effect` oracle trusts that the backend honors `idempotency_key`; without one,
  duplicate detection is based on identical call arguments.
- `examples/real_sdk_check.py` is a manual script (needs real API keys via `.env`, see
  `.env.example`), not part of `pytest` — the core test suite stays offline and key-free by design.
- Faults apply per-call; there is no multi-step storyline/composition yet (planned for v1.0).
- New capabilities are meant to land as plugins/scenario packs, not core changes — see
  `docs/ROADMAP.md`'s stated rule, before adding core surface area.
