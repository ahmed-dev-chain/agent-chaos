"""Framework-agnostic tool wrapping, shared by every adapter.

Duck-typed against the two shapes agent tool libraries actually use: a plain ``func``/``coroutine``
pair (LangChain's ``StructuredTool``) or direct ``_run``/``_arun`` methods (any custom ``BaseTool``
subclass, including LangChain's and CrewAI's). No hard dependency on either library.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

from ..core.context import RunContext
from ..core.events import Kind

T = TypeVar("T")


def wrap_tool(ctx: RunContext, tool: T, *, side_effect: bool = False) -> T:
    """Wrap a single tool object in place, returning it for chaining.

    Rewrites ``func``/``coroutine`` when present (LangChain's ``Tool``/``StructuredTool``). For a
    tool that instead overrides ``_run``/``_arun`` directly (a custom ``BaseTool`` subclass, the
    shape CrewAI tools always use), those are wrapped instead -- whichever attributes the tool
    actually has. A tool with none of the four is returned untouched.
    """
    name = getattr(tool, "name", None) or getattr(tool, "__name__", None) or str(tool)

    func = getattr(tool, "func", None)
    if func is not None:
        tool.func = ctx.wrap(name, func, kind=Kind.TOOL_CALL, side_effect=side_effect)
    else:
        run = getattr(tool, "_run", None)
        if callable(run):
            tool._run = ctx.wrap(name, run, kind=Kind.TOOL_CALL, side_effect=side_effect)

    coroutine = getattr(tool, "coroutine", None)
    if coroutine is not None:
        tool.coroutine = ctx.awrap(name, coroutine, kind=Kind.TOOL_CALL, side_effect=side_effect)
    else:
        arun = getattr(tool, "_arun", None)
        if callable(arun):
            tool._arun = ctx.awrap(name, arun, kind=Kind.TOOL_CALL, side_effect=side_effect)

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
