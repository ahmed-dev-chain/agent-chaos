"""Tests for the LangGraph/LangChain adapter, using duck-typed fakes.

No langgraph/langchain-core dependency needed: the adapter only relies on the documented shape
of a node function (any callable) and a LangChain tool (``name`` + ``func``/``coroutine``
attributes), so plain fakes exercise the same code paths real objects would.
"""
import asyncio
from types import SimpleNamespace

import pytest

from agent_chaos import Kind, RunContext, ToolTimeout, faults
from agent_chaos.adapters.langgraph import wrap_node, wrap_tool, wrap_tools


def make_ctx(fault_list, seed=1):
    return RunContext(seed, fault_list)


def test_wrap_node_sync_goes_through_fault_engine():
    ctx = make_ctx([faults.Timeout("tool=search")])

    def search_node(state):
        return {"results": ["a"]}

    node = wrap_node(ctx, "search", search_node)
    with pytest.raises(ToolTimeout):
        node({"query": "x"})
    assert not ctx.events[0].executed


def test_wrap_node_sync_passthrough():
    ctx = make_ctx([])

    def search_node(state):
        return {"results": [state["query"]]}

    node = wrap_node(ctx, "search", search_node)
    assert node({"query": "x"}) == {"results": ["x"]}


def test_wrap_node_model_kind():
    ctx = make_ctx([])

    def call_model(state):
        return {"reply": "ok"}

    node = wrap_node(ctx, "call_model", call_model, kind=Kind.MODEL_CALL)
    node({"q": 1})
    assert ctx.events[0].kind == Kind.MODEL_CALL


def test_wrap_node_async():
    ctx = make_ctx([faults.Refusal("tool=call_model")])

    async def call_model(state):
        return {"reply": "real"}

    node = wrap_node(ctx, "call_model", call_model)
    out = asyncio.run(node({"q": 1}))
    assert out == "I'm sorry, I can't help with that request."
    assert not ctx.events[0].executed


def _fake_tool(name, func=None, coroutine=None):
    return SimpleNamespace(name=name, func=func, coroutine=coroutine)


def test_wrap_tool_wraps_func_and_coroutine():
    ctx = make_ctx([faults.ErrorStatus("tool=refund")])

    async def arefund(order_id):
        return {"ok": True}

    tool = _fake_tool("refund", func=lambda order_id: {"ok": True}, coroutine=arefund)
    wrap_tool(ctx, tool, side_effect=True)

    from agent_chaos import ToolError

    with pytest.raises(ToolError):
        tool.func(order_id=1)
    assert ctx.events[0].side_effect

    with pytest.raises(ToolError):
        asyncio.run(tool.coroutine(order_id=1))


def test_wrap_tool_without_func_or_coroutine_is_untouched():
    ctx = make_ctx([])
    tool = SimpleNamespace(name="custom")  # no func/coroutine attrs
    out = wrap_tool(ctx, tool)
    assert out is tool and not ctx.events


def test_wrap_tools_predicate_side_effect():
    ctx = make_ctx([])
    read_tool = _fake_tool("search", func=lambda q: q)
    write_tool = _fake_tool("refund", func=lambda order_id: order_id)

    wrap_tools(ctx, [read_tool, write_tool], side_effect=lambda t: t.name == "refund")
    read_tool.func(q="x")
    write_tool.func(order_id=1)

    assert ctx.events[0].side_effect is False
    assert ctx.events[1].side_effect is True
