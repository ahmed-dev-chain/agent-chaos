"""LangGraph adapter: wrap graph nodes and LangChain tools so they go through the fault engine.

``wrap_node`` is specific to LangGraph; tool wrapping (``wrap_tool``/``wrap_tools``, re-exported
here for backward compatibility) is shared with the other adapters -- see ``adapters/tools.py``.
No hard dependency on LangGraph/LangChain: everything here is duck-typed.

    from agent_chaos.adapters.langgraph import wrap_node, wrap_tools

    graph = StateGraph(State)
    graph.add_node("search", wrap_node(ctx, "search", search_node))
    graph.add_node("call_model", wrap_node(ctx, "call_model", call_model_node, kind=Kind.MODEL_CALL))
    wrap_tools(ctx, [search_tool, refund_tool], side_effect=lambda t: t.name == "refund_tool")
"""
from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from ..core.context import RunContext
from ..core.events import Kind
from .tools import wrap_tool, wrap_tools  # noqa: F401 - re-exported for backward compatibility


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
