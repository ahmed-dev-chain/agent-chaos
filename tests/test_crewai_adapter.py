"""Tests for the CrewAI adapter's own import path, using a fake BaseTool-shaped object
(name + _run/_arun, no func/coroutine -- CrewAI's actual custom-tool shape).
"""
import asyncio

import pytest

from agent_chaos import RunContext, ToolError, faults
from agent_chaos.adapters.crewai import wrap_tool, wrap_tools
from agent_chaos.adapters.tools import wrap_tool as shared_wrap_tool


def make_ctx(fault_list, seed=1):
    return RunContext(seed, fault_list)


class _CrewAIStyleTool:
    name = "refund"

    def _run(self, order_id):
        return {"ok": True, "order_id": order_id}

    async def _arun(self, order_id):
        return {"ok": True, "order_id": order_id}


def test_crewai_wrap_tool_is_the_shared_implementation():
    assert wrap_tool is shared_wrap_tool


def test_crewai_tool_run_is_intercepted():
    ctx = make_ctx([faults.ErrorStatus("tool=refund")])
    tool = _CrewAIStyleTool()
    wrap_tool(ctx, tool, side_effect=True)

    with pytest.raises(ToolError):
        tool._run(order_id=1)
    assert ctx.events[0].side_effect


def test_crewai_tool_arun_passthrough():
    ctx = make_ctx([])
    tool = _CrewAIStyleTool()
    wrap_tool(ctx, tool)
    assert asyncio.run(tool._arun(order_id=7)) == {"ok": True, "order_id": 7}


def test_crewai_wrap_tools_list():
    ctx = make_ctx([])
    tools = [_CrewAIStyleTool()]
    wrap_tools(ctx, tools)
    tools[0]._run(order_id=1)
    assert ctx.events[0].name == "refund"
