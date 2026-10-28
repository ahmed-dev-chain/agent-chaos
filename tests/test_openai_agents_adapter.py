"""Tests for the OpenAI Agents SDK adapter, using a fake matching FunctionTool's documented shape
(name + always-async on_invoke_tool(ctx, args_json)). No openai-agents/agents dependency needed.
"""
import asyncio
from types import SimpleNamespace

import pytest

from agent_chaos import RunContext, ToolTimeout, faults
from agent_chaos.adapters.openai_agents import wrap_function_tool, wrap_function_tools


def make_ctx(fault_list, seed=1):
    return RunContext(seed, fault_list)


def _fake_function_tool(name, on_invoke_tool):
    return SimpleNamespace(name=name, on_invoke_tool=on_invoke_tool)


def test_wrap_function_tool_passthrough():
    ctx = make_ctx([])

    async def invoke(run_ctx, args_json):
        return f"handled:{args_json}"

    tool = _fake_function_tool("search", invoke)
    wrap_function_tool(ctx, tool)

    out = asyncio.run(tool.on_invoke_tool(object(), '{"q": "x"}'))
    assert out == 'handled:{"q": "x"}'
    assert ctx.events[0].name == "search" and ctx.events[0].executed


def test_wrap_function_tool_intercepted_by_fault():
    ctx = make_ctx([faults.Timeout("tool=search")])
    ran = []

    async def invoke(run_ctx, args_json):
        ran.append(1)
        return "real"

    tool = _fake_function_tool("search", invoke)
    wrap_function_tool(ctx, tool)

    with pytest.raises(ToolTimeout):
        asyncio.run(tool.on_invoke_tool(object(), "{}"))
    assert not ran and not ctx.events[0].executed


def test_wrap_function_tools_side_effect_predicate():
    ctx = make_ctx([])

    async def noop(run_ctx, args_json):
        return "ok"

    read_tool = _fake_function_tool("search", noop)
    write_tool = _fake_function_tool("refund", noop)
    wrap_function_tools(ctx, [read_tool, write_tool], side_effect=lambda t: t.name == "refund")

    asyncio.run(read_tool.on_invoke_tool(object(), "{}"))
    asyncio.run(write_tool.on_invoke_tool(object(), "{}"))

    assert ctx.events[0].side_effect is False
    assert ctx.events[1].side_effect is True


def test_wrap_function_tool_without_on_invoke_tool_is_untouched():
    ctx = make_ctx([])
    tool = SimpleNamespace(name="custom")
    out = wrap_function_tool(ctx, tool)
    assert out is tool and not ctx.events
