"""``chaos init``: detect the agent framework in the current project and write a starter scenario file."""
from __future__ import annotations

import importlib.util

_FRAMEWORK_SPECS = (
    ("langgraph", "langgraph"),
    ("langchain_core", "langchain"),
)


def detect_framework() -> str:
    """Best-effort guess at the installed agent framework, or ``"plain"`` if none is found."""
    for module_name, label in _FRAMEWORK_SPECS:
        try:
            if importlib.util.find_spec(module_name) is not None:
                return label
        except (ImportError, ValueError):
            continue
    return "plain"


_HEADER = '''"""Starter agent-chaos scenario file (detected framework: {framework}).

Edit TARGET and TASK below for your real agent, then:

    chaos run {out}
    chaos run {out} --min-score 95   # as a CI gate
"""
'''

_PLAIN_BODY = '''from agent_chaos import Scenario, faults, oracles, policies


def my_agent(task: str, ctx) -> dict:
    """Replace this with a call into your real agent.

    Wrap every tool or API call with ``ctx.wrap(name, fn, side_effect=...)`` (or ``ctx.awrap``
    for an async tool) so agent-chaos can inject faults into it. Mark calls that have a real-world
    side effect (payments, emails, writes) with ``side_effect=True``.
    """
    search = ctx.wrap("search", lambda query: {"result": f"...about {query}"})
    return {"answer": search(query=task)}


TASK = "Describe the task your agent should complete"

SCENARIOS = [
    Scenario(
        name="tool_timeout",
        target=my_agent,
        task=TASK,
        faults=[faults.Timeout("tool=search", policies.Probability(0.4))],
        oracles=[oracles.max_steps(20)],
        trials=20,
    ),
    Scenario(
        name="malformed_output",
        target=my_agent,
        task=TASK,
        faults=[faults.MalformedOutput("tool=search", policies.Probability(0.4))],
        oracles=[oracles.max_steps(20)],
        trials=20,
    ),
]
'''

_LANGGRAPH_BODY = '''from agent_chaos import RunContext, Scenario, faults, oracles, policies
from agent_chaos.adapters.langgraph import wrap_node, wrap_tools

# from your_agent_module import build_graph, tools  # <- replace with your real graph and tools


def my_agent(task: str, ctx: RunContext) -> dict:
    """Replace this with your real LangGraph graph.

    Wrap every node with ``wrap_node`` and every tool with ``wrap_tools`` *before* calling
    ``.compile()``, so agent-chaos can inject faults into them:

        graph = build_graph()
        graph.add_node("search", wrap_node(ctx, "search", search_node))
        wrap_tools(ctx, tools, side_effect=lambda t: t.name in {"refund", "send_email"})
        compiled = graph.compile()
        return compiled.invoke({"input": task})
    """
    raise NotImplementedError("wire up your real LangGraph graph here")


TASK = "Describe the task your agent should complete"

SCENARIOS = [
    Scenario(
        name="tool_timeout",
        target=my_agent,
        task=TASK,
        faults=[faults.Timeout("tool=search", policies.Probability(0.4))],
        oracles=[oracles.max_steps(20)],
        trials=20,
    ),
]
'''

_LANGCHAIN_BODY = '''from agent_chaos import RunContext, Scenario, faults, oracles, policies
from agent_chaos.adapters.langgraph import wrap_tools

# from your_agent_module import build_agent_executor, tools  # <- replace with your real agent


def my_agent(task: str, ctx: RunContext) -> dict:
    """Replace this with your real LangChain agent.

    Wrap every tool with ``wrap_tools`` *before* building the agent executor, so agent-chaos can
    inject faults into them:

        wrap_tools(ctx, tools, side_effect=lambda t: t.name in {"refund", "send_email"})
        executor = build_agent_executor(tools)
        return executor.invoke({"input": task})
    """
    raise NotImplementedError("wire up your real LangChain agent here")


TASK = "Describe the task your agent should complete"

SCENARIOS = [
    Scenario(
        name="tool_timeout",
        target=my_agent,
        task=TASK,
        faults=[faults.Timeout("tool=search", policies.Probability(0.4))],
        oracles=[oracles.max_steps(20)],
        trials=20,
    ),
]
'''

_BODIES = {"plain": _PLAIN_BODY, "langchain": _LANGCHAIN_BODY, "langgraph": _LANGGRAPH_BODY}


def render_template(framework: str, out_name: str) -> str:
    body = _BODIES.get(framework, _PLAIN_BODY)
    return _HEADER.format(framework=framework, out=out_name) + "\n" + body
