"""OpenAI Agents SDK adapter: wrap a FunctionTool so it runs through the fault engine.

A ``@function_tool``-decorated function becomes a ``FunctionTool`` with a stable ``name`` and an
always-async ``on_invoke_tool(ctx, args_json)`` -- the one true invocation entrypoint the SDK's
runner calls. Duck-typed, no hard dependency on ``openai-agents``/``agents``.

    from agent_chaos.adapters.openai_agents import wrap_function_tools

    tools = wrap_function_tools(ctx, [search_tool, refund_tool],
                                 side_effect=lambda t: t.name == "refund_tool")
    agent = Agent(name="support", tools=tools)
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

from ..core.context import RunContext
from ..core.events import Kind

T = TypeVar("T")


def wrap_function_tool(ctx: RunContext, tool: T, *, side_effect: bool = False) -> T:
    """Wrap a single FunctionTool's ``on_invoke_tool`` in place, returning it for chaining."""
    name = getattr(tool, "name", None) or getattr(tool, "__name__", None) or str(tool)
    invoke = getattr(tool, "on_invoke_tool", None)
    if invoke is not None:
        tool.on_invoke_tool = ctx.awrap(name, invoke, kind=Kind.TOOL_CALL, side_effect=side_effect)
    return tool


def wrap_function_tools(
    ctx: RunContext,
    tools: Iterable[T],
    *,
    side_effect: Callable[[T], bool] | bool = False,
) -> list[T]:
    """Wrap every tool in ``tools`` (see :func:`wrap_function_tool`).

    ``side_effect`` is either a flat bool or a predicate called with each tool, for a mixed list
    of read and write tools.
    """
    return [wrap_function_tool(ctx, tool, side_effect=side_effect(tool) if callable(side_effect) else side_effect)
            for tool in tools]
