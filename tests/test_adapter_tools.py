"""Tests for the shared adapters.tools wrapping, especially the _run/_arun fallback that
LangChain's adapters/langgraph.py previously couldn't cover for custom BaseTool subclasses.
"""
import asyncio
from types import SimpleNamespace

import pytest

from agent_chaos import RunContext, ToolError, faults
from agent_chaos.adapters.langgraph import wrap_tool as langgraph_wrap_tool  # backward-compat import
from agent_chaos.adapters.tools import wrap_tool, wrap_tools


def make_ctx(fault_list, seed=1):
    return RunContext(seed, fault_list)


class _BaseToolLike:
    """Mimics a custom BaseTool subclass: _run/_arun defined directly, no func/coroutine."""

    name = "refund"

    def _run(self, order_id):
        return {"ok": True, "order_id": order_id}

    async def _arun(self, order_id):
        return {"ok": True, "order_id": order_id}


def test_run_arun_fallback_is_wrapped():
    ctx = make_ctx([faults.ErrorStatus("tool=refund")])
    tool = _BaseToolLike()
    wrap_tool(ctx, tool, side_effect=True)

    with pytest.raises(ToolError):
        tool._run(order_id=1)
    assert ctx.events[0].side_effect

    with pytest.raises(ToolError):
        asyncio.run(tool._arun(order_id=1))


def test_run_arun_passthrough_without_faults():
    ctx = make_ctx([])
    tool = _BaseToolLike()
    wrap_tool(ctx, tool)
    assert tool._run(order_id=5) == {"ok": True, "order_id": 5}
    assert asyncio.run(tool._arun(order_id=5)) == {"ok": True, "order_id": 5}


def test_func_coroutine_still_preferred_over_run_arun():
    ctx = make_ctx([faults.Refusal("tool=search", message="no")])
    tool = SimpleNamespace(name="search", func=lambda q: q, _run=lambda q: "should not be used")
    wrap_tool(ctx, tool)
    assert tool.func(q="x") == "no"
    assert tool._run("x") == "should not be used"  # untouched: func took precedence


def test_wrap_tools_handles_mixed_shapes():
    ctx = make_ctx([])
    func_tool = SimpleNamespace(name="search", func=lambda q: q)
    run_tool = _BaseToolLike()
    wrap_tools(ctx, [func_tool, run_tool])
    func_tool.func(q="x")
    run_tool._run(order_id=1)
    assert [e.name for e in ctx.events] == ["search", "refund"]


def test_langgraph_module_reexports_same_function():
    assert langgraph_wrap_tool is wrap_tool
