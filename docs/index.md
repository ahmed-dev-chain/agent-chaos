# agent-chaos

**Chaos engineering for AI agents.** Your agent works in the demo. Does it work when everything
breaks?

agent-chaos deliberately breaks the things your agent depends on — tools, APIs, models, context —
then tells you exactly how it failed and whether it did anything dangerous. You get a resilience
score, a reproducible trace for every failure, and an exit code your CI can enforce.

Netflix's Chaos Monkey did this for servers. Almost nobody does it for agents, and agents fail in
exactly the ways servers do: timeouts, retries, partial failures, poisoned inputs. The difference
is that an agent can also be talked into doing something it should never do.

- **Deterministic**: every trial has a seed. Any failure replays exactly, offline, with one command.
- **Safety-aware**: duplicate charges and obeyed prompt injections count as `unsafe` and block the gate.
- **Zero dependencies**: the core is pure Python 3.10+. No API key needed to try it.
- **Plugin-first**: faults, oracles, adapters and reporters are small classes anyone can add.

## Where to go next

- [Quickstart](quickstart.md) — install it and watch an agent fail, then survive
- [Fault reference](faults.md) — the full catalog, by category
- [Architecture](ARCHITECTURE.md) — how the layers fit together, and what's not built yet
- [Roadmap](ROADMAP.md) — what's shipped and what's next
- [Stability policy](STABILITY.md) — what's safe to build against today

The full pitch, demo output and feature comparison live in the
[project README](https://github.com/ahmed-dev-chain/agent-chaos#readme).
