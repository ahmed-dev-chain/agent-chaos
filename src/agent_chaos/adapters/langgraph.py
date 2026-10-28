"""LangGraph adapter: wrap graph nodes and LangChain tools so they go through the fault engine.

LangGraph node functions and LangChain tools are plain callables with a well-defined call
signature, so this adapter needs no LangGraph/LangChain internals and no hard dependency on
either package (everything here is duck-typed): wrap each node's function before handing it to
``StateGraph.add_node``, and wrap each tool's ``func``/``coroutine`` in place.

    from agent_chaos.adapters.langgraph import wrap_node, wrap_tools

    graph = StateGraph(State)
    graph.add_node("search", wrap_node(ctx, "search", search_node))
    graph.add_node("call_model", wrap_node(ctx, "call_model", call_model_node, kind=Kind.MODEL_CALL))
    wrap_tools(ctx, [search_tool, refund_tool], side_effect=lambda t: t.name == "refund_tool")
"""
from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

from ..core.context import RunContext
from ..core.events import Kind

T = TypeVar("T")


def wrap_node(
    ctx: RunContext,
    name: str,
    fn: Callable[..., Any],
    *,
    kind: Kind = Kind.TOOL_CALL,
    side_effect: bool = False,
) -> Callable[..., Any]:
    """Wrap a LangGraph node function (sync or async) so it runs through the fault engine."""
    if inspect.iscoroutinefunction(fn):
        return ctx.awrap(name, fn, kind=kind, side_effect=side_effect)
    return ctx.wrap(name, fn, kind=kind, side_effect=side_effect)


def wrap_tool(ctx: RunContext, tool: T, *, side_effect: bool = False) -> T:
    """Wrap a single LangChain tool (``Tool``/``StructuredTool``/custom ``BaseTool``) in place.

    Rewrites the tool's ``func`` and, if present, ``coroutine`` attribute to go through the fault
    engine, keyed by the tool's own ``name``, then returns the same tool for chaining. A tool with
    neither attribute (a ``BaseTool`` subclass that overrides ``_run``/``_arun`` directly instead
    of setting ``func``/``coroutine``) is returned untouched -- wrap those by hand with
    :func:`wrap_node` around whatever callable backs its ``_run``.
    """
    name = getattr(tool, "name", None) or getattr(tool, "__name__", None) or str(tool)
    func = getattr(tool, "func", None)
    if func is not None:
        tool.func = ctx.wrap(name, func, kind=Kind.TOOL_CALL, side_effect=side_effect)
    coroutine = getattr(tool, "coroutine", None)
    if coroutine is not None:
        tool.coroutine = ctx.awrap(name, coroutine, kind=Kind.TOOL_CALL, side_effect=side_effect)
    return tool


def wrap_tools(
    ctx: RunContext,
    tools: Iterable[T],
    *,
    side_effect: Callable[[T], bool] | bool = False,
) -> list[T]:
    """Wrap every tool in ``tools`` (see :func:`wrap_tool`).

    ``side_effect`` is either a flat bool or a predicate called with each tool, for a mixed list
    of read and write tools (e.g. ``side_effect=lambda t: t.name in {"refund", "send_email"}``).
    """
    return [wrap_tool(ctx, tool, side_effect=side_effect(tool) if callable(side_effect) else side_effect)
            for tool in tools]
