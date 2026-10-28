# Roadmap

Rule: new capability arrives as a plugin or scenario pack, never as a core change.

## Next (v0.2): works with real agents
- [x] Model faults: refusal, format drift, truncation
- [x] Context faults: window overflow, memory corruption
- [x] httpx async client patch; verify against real OpenAI/Anthropic SDK calls (`examples/real_sdk_check.py`)
- [x] LangGraph adapter (node and tool level)
- [x] `chaos init` that detects the framework and writes a starter scenario file
- [x] OpenAI Agents SDK and CrewAI adapters

## v0.5: works with anything
- [x] Trajectory oracles (tool order, retry limits, loop detection)
- [x] Record and replay for free, deterministic CI
- [ ] Transparent proxy (HTTP, SSE streaming, MCP) for any language

## v1.0: trustworthy
- [x] Written stability policy (`docs/STABILITY.md`) -- actually *frozen* still waits for 1.0.0 itself
- [x] SARIF and JUnit XML output
- [x] Failure shrinking: `chaos shrink` reduces a failing trial's faults to the smallest reproducing set
- [ ] GitHub Action with PR comment and score diff
- [ ] Baselines and trend tracking
- [ ] Calibrated LLM-judge oracle (optional)
- [ ] Docs site and public benchmark of popular agent templates

## Later
Adaptive adversary, multi-agent faults, RAG and memory faults, browser faults, hosted dashboard, compliance packs.
