"""SDK-level interception: route every httpx request through the fault engine.

Because the OpenAI and Anthropic Python SDKs use httpx under the hood, this single patch
covers model calls and most tool/API traffic with no changes to the agent.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from ..core.context import RunContext
from ..core.errors import ToolError, ToolTimeout
from ..core.events import Kind

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@contextmanager
def patch_httpx(ctx: RunContext) -> Iterator[None]:
    """Patch both ``httpx.Client`` (sync) and ``httpx.AsyncClient`` (async) for the duration of the block."""
    import httpx  # optional dependency

    original_sync = httpx.Client.send
    original_async = httpx.AsyncClient.send

    def send(self: httpx.Client, request: httpx.Request, **kwargs):  # type: ignore[no-untyped-def]
        try:
            return ctx.call(
                Kind.HTTP,
                f"{request.method} {request.url.host}",
                lambda: original_sync(self, request, **kwargs),
                args={"url": str(request.url)},
                side_effect=request.method not in _SAFE_METHODS,
                idempotency_key=request.headers.get("idempotency-key"),
            )
        except ToolError as exc:
            return httpx.Response(exc.status, request=request, text=str(exc))
        except ToolTimeout as exc:
            raise httpx.ReadTimeout(str(exc), request=request) from exc

    async def asend(self: httpx.AsyncClient, request: httpx.Request, **kwargs):  # type: ignore[no-untyped-def]
        try:
            return await ctx.acall(
                Kind.HTTP,
                f"{request.method} {request.url.host}",
                lambda: original_async(self, request, **kwargs),
                args={"url": str(request.url)},
                side_effect=request.method not in _SAFE_METHODS,
                idempotency_key=request.headers.get("idempotency-key"),
            )
        except ToolError as exc:
            return httpx.Response(exc.status, request=request, text=str(exc))
        except ToolTimeout as exc:
            raise httpx.ReadTimeout(str(exc), request=request) from exc

    httpx.Client.send = send  # type: ignore[method-assign]
    httpx.AsyncClient.send = asend  # type: ignore[method-assign]
    try:
        yield
    finally:
        httpx.Client.send = original_sync  # type: ignore[method-assign]
        httpx.AsyncClient.send = original_async  # type: ignore[method-assign]
