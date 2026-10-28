# Roadmap

Rule: new capability arrives as a plugin or scenario pack, never as a core change.

## Next (v0.2): works with real agents
- [x] Model faults: refusal, format drift, truncation
- [x] Context faults: window overflow, memory corruption
- [x] httpx async client patch; verify against real OpenAI/Anthropic SDK calls (`examples/real_sdk_check.py`)
- [ ] LangGraph adapter (node and tool level)
- [ ] LangChain and OpenAI Agents SDK adapters
- [ ] `chaos init` that detects the framework and writes a starter scenario file

## v0.5: works with anything
- [ ] Transparent proxy (HTTP, SSE streaming, MCP) for any language
- [ ] Record and replay for free, deterministic CI
- [ ] Trajectory oracles (tool order, retry limits, loop detection)

## v1.0: trustworthy
- [ ] Frozen public API and written stability policy
- [ ] GitHub Action with PR comment and score diff
- [ ] Baselines and trend tracking, SARIF and JUnit output
- [ ] Calibrated LLM-judge oracle (optional)
- [ ] Docs site and public benchmark of popular agent templates

## Later
Adaptive adversary, failure shrinking, multi-agent faults, RAG and memory faults, browser faults, hosted dashboard, compliance packs.
