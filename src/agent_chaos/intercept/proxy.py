"""Transparent forward proxy: point any process's HTTP(S)_PROXY at this and its traffic flows
through the same fault engine as ``ctx.wrap``/``patch_httpx`` -- works with any language, not just
in-process Python.

Only hosts in ``allow_hosts`` are decrypted and fault-tested (see ``_connect.py``, added in a
later phase, for the HTTPS/CONNECT side); this module handles plain HTTP. stdlib ``asyncio`` only
-- the ``cryptography`` dependency lives in ``proxy_ca.py`` and is only needed for HTTPS.
"""
from __future__ import annotations

import asyncio
import ssl
import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from ..core.context import RunContext
from ..core.errors import ToolError, ToolTimeout
from ..core.events import Kind

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_MAX_HEADER_BYTES = 64 * 1024


class ProxyResponse:
    """Minimal httpx.Response-alike: enough shape for faults/tool.py's ``_corrupt`` to work on it
    (``status_code``, ``content``, reconstructable as ``type(value)(status_code, content=..., request=...)``).
    """

    def __init__(self, status_code: int, *, content: bytes = b"", headers: dict[str, str] | None = None,
                 request: Any = None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.request = request


@dataclass
class ProxyHandle:
    url: str
    env: dict[str, str] = field(default_factory=dict)


async def _read_headers(reader: asyncio.StreamReader) -> bytes:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = await reader.read(4096)
        if not chunk:
            break
        data += chunk
        if len(data) > _MAX_HEADER_BYTES:
            raise ValueError("request headers too large")
    return data


def _parse_headers(raw: bytes) -> tuple[str, dict[str, str]]:
    head, _, _ = raw.partition(b"\r\n\r\n")
    lines = head.decode("latin-1").split("\r\n")
    start_line = lines[0]
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return start_line, headers


async def _read_body(reader: asyncio.StreamReader, prefetched: bytes, headers: dict[str, str]) -> bytes:
    if "content-length" in headers:
        length = int(headers["content-length"])
        body = prefetched
        while len(body) < length:
            chunk = await reader.read(length - len(body))
            if not chunk:
                break
            body += chunk
        return body[:length]
    if headers.get("transfer-encoding", "").lower() == "chunked":
        return await _read_chunked(reader, prefetched)
    return prefetched


async def _read_chunked(reader: asyncio.StreamReader, prefetched: bytes) -> bytes:
    buf = prefetched
    out = b""
    while True:
        while b"\r\n" not in buf:
            chunk = await reader.read(4096)
            if not chunk:
                return out
            buf += chunk
        size_line, _, buf = buf.partition(b"\r\n")
        size = int(size_line.split(b";")[0], 16)
        if size == 0:
            return out
        while len(buf) < size + 2:
            chunk = await reader.read(size + 2 - len(buf))
            if not chunk:
                return out
            buf += chunk
        out += buf[:size]
        buf = buf[size + 2:]


async def _fetch(host: str, port: int, method: str, target: str, headers: dict[str, str], body: bytes,
                  *, use_tls: bool = False) -> ProxyResponse:
    if use_tls:
        reader, writer = await asyncio.open_connection(host, port, ssl=ssl.create_default_context())
    else:
        reader, writer = await asyncio.open_connection(host, port)
    try:
        out_headers = dict(headers)
        out_headers["host"] = host if port in (80, 443) else f"{host}:{port}"
        out_headers["connection"] = "close"
        if body:
            out_headers["content-length"] = str(len(body))
        req = f"{method} {target} HTTP/1.1\r\n"
        req += "".join(f"{k}: {v}\r\n" for k, v in out_headers.items())
        req += "\r\n"
        writer.write(req.encode("latin-1") + body)
        await writer.drain()

        raw = await _read_headers(reader)
        start_line, resp_headers = _parse_headers(raw)
        prefetched = raw.partition(b"\r\n\r\n")[2]
        status_code = int(start_line.split(" ", 2)[1])
        resp_body = await _read_body(reader, prefetched, resp_headers)
        return ProxyResponse(status_code, content=resp_body, headers=resp_headers)
    finally:
        writer.close()


def _serialize_response(resp: ProxyResponse) -> bytes:
    headers = dict(resp.headers)
    headers.pop("transfer-encoding", None)
    headers["content-length"] = str(len(resp.content))
    headers["connection"] = "close"
    reason = {200: "OK", 404: "Not Found", 500: "Internal Server Error", 503: "Service Unavailable"}
    head = f"HTTP/1.1 {resp.status_code} {reason.get(resp.status_code, 'OK')}\r\n"
    head += "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    head += "\r\n"
    return head.encode("latin-1") + resp.content


async def proxy_one_request(ctx: RunContext, host: str, port: int, use_tls: bool, method: str, path: str,
                             url: str, headers: dict[str, str], body: bytes, writer: asyncio.StreamWriter) -> None:
    """Run one already-parsed request through the fault engine and write the response back.

    Shared by plain HTTP (absolute-URI, this module) and decrypted post-CONNECT HTTPS
    (origin-form, ``proxy_connect.py``) -- same event, same fault application either way.
    """
    name = f"{method} {host}"
    try:
        resp = await ctx.acall(
            Kind.HTTP, name,
            lambda: _fetch(host, port, method, path, headers, body, use_tls=use_tls),
            args={"url": url},
            side_effect=method not in _SAFE_METHODS,
            idempotency_key=headers.get("idempotency-key"),
        )
        writer.write(_serialize_response(resp))
    except ToolError as exc:
        writer.write(_serialize_response(ProxyResponse(exc.status, content=str(exc).encode())))
    except ToolTimeout:
        pass  # close without responding: the client sees it as a timed-out/dropped connection
    await writer.drain()


async def _handle_plain_http(ctx: RunContext, start_line: str, headers: dict[str, str], body: bytes,
                              writer: asyncio.StreamWriter) -> None:
    method, target, _ = start_line.split(" ", 2)
    parts = urlsplit(target)
    host = parts.hostname or headers.get("host", "").split(":")[0]
    port = parts.port or 80
    path = parts.path or "/"
    if parts.query:
        path += f"?{parts.query}"
    await proxy_one_request(ctx, host, port, False, method, path, target, headers, body, writer)


async def _connection_handler(ctx: RunContext, allow_hosts: Sequence[str],
                               reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        raw = await _read_headers(reader)
        if not raw:
            return
        start_line, headers = _parse_headers(raw)
        prefetched = raw.partition(b"\r\n\r\n")[2]
        method = start_line.split(" ", 1)[0]

        if method == "CONNECT":
            try:
                from .proxy_connect import handle_connect  # added in a later phase; needs cryptography
            except ImportError:
                writer.write(b"HTTP/1.1 501 Not Implemented\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                return
            await handle_connect(ctx, allow_hosts, start_line, reader, writer, prefetched)
            return

        body = await _read_body(reader, prefetched, headers)
        await _handle_plain_http(ctx, start_line, headers, body, writer)
    except (ConnectionError, ValueError, OSError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


class _ProxyServerThread(threading.Thread):
    def __init__(self, ctx: RunContext, allow_hosts: Sequence[str], host: str, port: int):
        super().__init__(daemon=True)
        self.ctx = ctx
        self.allow_hosts = list(allow_hosts)
        self.host = host
        self.requested_port = port
        self.actual_port: int | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self._server: asyncio.base_events.Server | None = None
        self._ready = threading.Event()

    def run(self) -> None:
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._serve())
        except asyncio.CancelledError:
            pass  # expected: stop() cancels serve_forever() to shut down cleanly

    async def _serve(self) -> None:
        self._server = await asyncio.start_server(
            lambda r, w: _connection_handler(self.ctx, self.allow_hosts, r, w),
            self.host, self.requested_port,
        )
        self.actual_port = self._server.sockets[0].getsockname()[1]
        self._ready.set()
        async with self._server:
            await self._server.serve_forever()

    def wait_ready(self, timeout: float = 5.0) -> None:
        if not self._ready.wait(timeout):
            raise TimeoutError("proxy server did not start in time")

    def stop(self) -> None:
        if self.loop and self._server:
            self.loop.call_soon_threadsafe(self._server.close)
        self.join(timeout=5)


def run_proxy(ctx: RunContext, allow_hosts: Sequence[str] = (), *, host: str = "127.0.0.1", port: int = 0):
    """Context manager: starts a local forward proxy for the duration of the ``with`` block.

    Only ``allow_hosts`` are decrypted/fault-tested over HTTPS and recorded as ``Event``s; every
    other host (including all plain HTTP in this phase) still proxies through the same engine --
    plain HTTP has nothing to decrypt, so it's always fault-tested regardless of the allow-list.
    Yields a :class:`ProxyHandle` with ``.url`` and ``.env`` (merge into a subprocess's environment).
    """
    return _ProxyContext(ctx, allow_hosts, host, port)


class _ProxyContext:
    def __init__(self, ctx: RunContext, allow_hosts: Sequence[str], host: str, port: int):
        self.ctx = ctx
        self.allow_hosts = allow_hosts
        self.host = host
        self.port = port
        self._thread: _ProxyServerThread | None = None

    def __enter__(self) -> ProxyHandle:
        self._thread = _ProxyServerThread(self.ctx, self.allow_hosts, self.host, self.port)
        self._thread.start()
        self._thread.wait_ready()
        url = f"http://{self.host}:{self._thread.actual_port}"
        env = {"HTTP_PROXY": url, "http_proxy": url, "HTTPS_PROXY": url, "https_proxy": url}
        return ProxyHandle(url=url, env=env)

    def __exit__(self, *exc_info: object) -> None:
        if self._thread:
            self._thread.stop()
