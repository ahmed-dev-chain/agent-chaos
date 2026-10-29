# Progress

Session-continuity log: what's done, what's next, and enough context to pick the work back up
without re-deriving it. For the full feature checklist see [`docs/ROADMAP.md`](docs/ROADMAP.md);
for technical detail and known limits per module see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
This file is the one to read first when a session starts with "continue."

**Last updated:** 2026-10-29. **Branch:** everything below is merged to `master` (fast-forwarded
from `feature/v0.2-real-agents`, now deleted-or-stale — start new work from `master`).

## Status at a glance

v0.2 ("works with real agents") and v0.5 ("works with anything") are **fully complete**. Every
v1.0 ("trustworthy") roadmap line is checked off too, each with an honestly-stated caveat where
"done" needed qualifying — see the table below. 157 tests passing, `ruff check` clean, zero
runtime dependencies in the core (optional extras: `real-sdk`, `proxy`, `docs`, `dev`).

**Published and installable**: `pip install agent-chaos-toolkit` / `pipx install agent-chaos-toolkit`
works for anyone, verified with real fresh-venv installs against the actual PyPI index
(`agent-chaos` itself was already taken by an unrelated project; import name `agent_chaos` and the
`chaos` command are unaffected). Releases publish automatically on any `v*` tag push via PyPI
Trusted Publishing (`.github/workflows/release.yml`, `RELEASING.md`) — no token ever stored as a
secret. The GitHub repo is now **public** (it had to be — PyPI's rendered README needs the banner/
screenshot images and badges to resolve via `raw.githubusercontent.com`/Actions badges, which 404
on a private repo regardless of URL scheme; this was the actual root cause of "broken images on
PyPI," not a markdown/path bug). Current release: `0.2.1` (`0.2.0`'s README is permanently broken
since PyPI won't let a published version's files be replaced — harmless, since `pip install`
always resolves to latest).

## Done

| Area | What shipped | Caveat, if any |
| --- | --- | --- |
| Model & context faults | `refusal`, `format_drift`, `truncation`, `window_overflow`, `memory_corruption` | — |
| Async support | `RunContext.acall`/`.awrap`, async `patch_httpx` | faulted async calls run on a worker thread, not concurrently (`docs/ARCHITECTURE.md`) |
| Framework adapters | LangGraph, LangChain, CrewAI, OpenAI Agents SDK — all duck-typed, no hard deps | — |
| `chaos init` | Scaffolds a starter scenario file, detects the framework | — |
| Trajectory oracles | `tool_order`, `max_retries`, `no_call_loop` | — |
| Record and replay | `chaos record`, `ReplayFault`, `load_replay` | replayed errors lose their exact exception type |
| SARIF / JUnit XML reports | `--sarif`, `--junit` on `chaos run` | — |
| Stability policy | `docs/STABILITY.md` | policy is written; the API itself isn't frozen until 1.0.0 |
| `chaos shrink` | Delta-debugs a failing scenario's faults to the smallest reproducing set | not guaranteed globally minimal (rng-order effects) |
| Pluggable `llm_judge` oracle | `oracles.llm_judge`/`calibrate` | agent-chaos makes no LLM call itself by design |
| File-based baselines | `--baseline`/`--update-baseline` | single snapshot, no history/trend over time |
| GitHub Action | `.github/workflows/chaos-pr.yml`, posts PR score-diff comments | now live now that `master` is merged |
| Docs site skeleton | `mkdocs.yml` + `docs/index.md`/`quickstart.md`/`faults.md` | not published to GitHub Pages |
| `agent_chaos.claude.call_claude` | Works via `ANTHROPIC_API_KEY` **or** a logged-in `claude` CLI subscription, no code change | CLI path shells out per call — fine for scripted checks, not high-throughput |
| Transparent proxy | `chaos proxy`, `intercept.proxy.run_proxy`, local CA, selective HTTPS MITM (allow-listed hosts only) | buffered responses (no true SSE streaming); MCP-over-stdio uncovered; `cryptography` not installed in CI, so proxy tests are importorskip-gated and currently skip there |
| README setup docs | Requirements, "which install do I need" extras table | — |
| PyPI publish | `agent-chaos-toolkit` on PyPI, trusted-publishing release pipeline, repo made public | `0.2.0` has a permanently broken README on PyPI (fixed in `0.2.1`); see note above |

Each of these was verified by hand against real traffic/processes, not just unit tests, per a
lesson learned mid-project: the first `ReplayFault` design and the first `proxy_connect.py`
TLS-upgrade both had real bugs that only a live run caught.

## What's next (prioritized)

Nothing here is started. Pick one and say so, or just say "continue" and the next session should
propose this list and ask which to tackle — these are genuinely different-shaped pieces of work,
not a single obvious next step.

1. **Install `cryptography` in CI** (`.github/workflows/ci.yml`, add `proxy` to the installed
   extras or a dedicated matrix leg) so `test_proxy_ca.py`/`test_proxy_connect.py`/`test_proxy_cli.py`
   actually run continuously instead of relying on the one-time manual verification from this
   session. Small, mechanical, no design decision needed — good first pick.
2. **True SSE/streaming passthrough** for the transparent proxy. Current proxy buffers every
   response fully; real streaming needs chunk-level forwarding with faults that can still operate
   on a stream (or explicitly opt out of streaming for a given `where` match). Nontrivial design
   work, not just an extension of the current buffering code.
3. **Trend tracking over time** for baselines (`baseline.py` currently holds one snapshot). Needs
   a storage decision (still file-based? SQLite? something in `.github/`?) — ask before building.
4. **Publish the docs site** to GitHub Pages (the `mkdocs.yml` skeleton already builds clean).
   Now easier since the repo is public (private repos need a paid plan for Pages). Still needs a
   decision on how (a `gh-pages` branch + Action, or `mkdocs gh-deploy` run by hand) and confirming
   you want Pages enabled (a repo-settings change) — ask first.
5. **MCP-over-stdio** fault injection. Different transport entirely (no network), would need its
   own interception strategy — not an extension of the proxy.
6. **"Later" bucket** (`docs/ROADMAP.md`): adaptive adversary, multi-agent faults, RAG/memory
   faults, browser faults, hosted dashboard, compliance packs. Each is a speculative v2+ system,
   not scoped — any of these needs a real planning pass (likely plan mode) before writing code,
   not just picking it up from this list.
7. **Public benchmark write-up** ("I chaos-tested N popular agent templates..."). This is research
   and writing, not an engineering task — picking real target repos, running them, reporting
   results honestly (notify maintainers first, per the blueprint's own guidance).

## Context worth knowing before continuing

- **Zero-dependency core is a hard constraint**, enforced via optional extras (`real-sdk`,
  `proxy`, `docs`) rather than growing `dependencies` in `pyproject.toml`. Any new feature needing
  a third-party package should default to this pattern unless there's a strong reason not to —
  ask first if unsure.
- **"New capability arrives as a plugin or scenario pack, never as a core change"** is the stated
  rule at the top of `docs/ROADMAP.md`. The few deliberate core touches so far (`RunContext.acall`,
  `Scenario.allow_hosts`) were each small, additive and backward-compatible — that bar should stay
  high.
- **Manual, real-world verification is mandatory for anything touching the network, TLS, or a
  subprocess** — unit tests alone missed two real bugs this session (a `ReplayFault` state bug, an
  `asyncio.start_tls` protocol-wiring bug). Don't skip the curl/httpbin-style check for proxy or
  interception work.
- **Git identity** is configured locally for this repo (`Muhammad Ahmed
  <66315915+ahmed-dev-chain@users.noreply.github.com>`). Commits are short, single-line, no
  co-author trailer (overrides the harness's default attribution footer, per explicit earlier
  instruction in this project).
- **`.github/workflows/chaos-pr.yml` is now live** (merged to `master`) — it'll comment on every
  future pull request using `.github/chaos-baseline.json` as the comparison point. Keep that
  baseline file updated (`chaos run examples/support_agent.py:HARDENED --baseline
  .github/chaos-baseline.json --update-baseline`) after any intentional change to the example's
  expected behavior.
