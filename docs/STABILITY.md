# Stability policy

agent-chaos is pre-1.0 (`0.1.0`). This document names the surface that's meant to stay stable and
the policy for changing it, now and after 1.0.

## The five stable extension interfaces

These are the contracts third-party faults, oracles, adapters and reporters build against (see
`docs/ARCHITECTURE.md`'s "Extension points" section):

| Interface | Where | Contract |
| --- | --- | --- |
| `Fault.apply` | `faults/base.py` | `apply(self, event: Event, ctx: RunContext, call: Callable[[], Any]) -> Any` |
| `Policy.should_fire` | `policies.py` | `should_fire(self, event: Event, ctx: RunContext) -> bool` |
| `Oracle.__call__` | `oracles/base.py` | `__call__(self, ctx: RunContext, result: Any) -> Verdict \| None` |
| `Scenario`/`RunContext` | `runner.py`, `core/context.py` | public fields/methods: `Scenario(name, target, task, faults, oracles, trials, seed, category, hard_step_cap)`; `RunContext.call`/`.acall`/`.wrap`/`.awrap`/`.rng`/`.events`/`.cost` |
| Reporters | `report/` | `render(summary) -> str` / `write_*(summary, path) -> Path`, taking a `RunSummary` and nothing else |

Also stable: the `Event`/`Verdict`/`Level` data shapes in `core/events.py` (including
`Event.to_dict()`'s JSON shape, since `record.py`'s replay and the JSON/SARIF/JUnit reporters all
depend on it), and the `agent_chaos.faults`/`agent_chaos.adapters` entry-point names used for
plugin discovery (`faults/base.py`'s `load_plugins`).

## Policy

- **Pre-1.0 (now)**: any of the above may still change. A change to one of them gets called out
  explicitly in the commit/PR description — this isn't a license to break things silently, just an
  acknowledgment that 0.x hasn't frozen yet.
- **At 1.0.0**: the surface above is frozen under semver. A breaking change requires a major
  version bump. A deprecation gets a warning and stays functional for two minor versions before
  removal.
- **Scenario files are a compatibility promise of their own**: once 1.0 ships, a `Scenario` list
  that runs under 1.0.0 keeps running, unmodified, on every later 1.x release.
- **Everything else is explicitly not covered**: private helpers (anything prefixed `_`, like
  `core.context._run_sync`), the terminal/HTML report's exact text or markup, and CLI flag spelling
  for anything added after 1.0 without a corresponding ROADMAP line.

New capabilities are meant to arrive as a new `Fault`/`Oracle`/adapter/reporter, not as a change to
one of the five interfaces themselves — see the "Rule" at the top of `docs/ROADMAP.md`. If a
feature genuinely can't be built that way, that's a sign the interface needs to grow, which is a
bigger, explicit decision, not something to do quietly inside an unrelated change.
