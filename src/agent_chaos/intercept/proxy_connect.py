"""HTTPS CONNECT handling: MITM-decrypt allow-listed hosts, opaquely tunnel everyone else.

Needs the ``cryptography`` package (via ``proxy_ca.py``) -- imported lazily from ``proxy.py`` so
plain-HTTP-only use never needs it.
"""
from __future__ import annotations

import asyncio
import ssl
import tempfile
from collections.abc import Sequence
from pathlib import Path

from ..core.context import RunContext
from .proxy import _parse_headers, _read_body, _read_headers, proxy_one_request
from .proxy_ca import CA, ensure_ca


class _TlsStreamReaderProtocol(asyncio.StreamReaderProtocol):
    """Suppresses asyncio's harmless "returning true from eof_received() has no effect when using
    ssl" warning -- the default StreamReaderProtocol.eof_received() return value is meaningless
    once wrapped in TLS, and asyncio logs a warning about it on every close otherwise."""

    def eof_received(self) -> bool:
        super().eof_received()
        return False


_ca: CA | None = None


def _get_ca() -> CA:
    global _ca
    if _ca is None:
        _ca = ensure_ca()
    return _ca


async def handle_connect(ctx: RunContext, allow_hosts: Sequence[str], start_line: str,
                          reader: asyncio.StreamReader, writer: asyncio.StreamWriter, prefetched: bytes) -> None:
    _, target, _ = start_line.split(" ", 2)
    host, _, port_s = target.partition(":")
    port = int(port_s) if port_s else 443

    if host not in allow_hosts:
        await _tunnel_opaque(host, port, reader, writer, prefetched)
        return

    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await writer.drain()

    ca = _get_ca()
    cert_pem, key_pem = ca.leaf_for(host)
    with tempfile.TemporaryDirectory() as tmp:
        cert_path = Path(tmp) / "leaf.pem"
        key_path = Path(tmp) / "leaf-key.pem"
        cert_path.write_bytes(cert_pem)
        key_path.write_bytes(key_pem)
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(str(cert_path), str(key_path))

        tls_reader, tls_writer = await _upgrade_to_tls_server(reader, writer, server_ctx)

    try:
        await _serve_decrypted_requests(ctx, host, port, tls_reader, tls_writer)
    except (ConnectionError, ValueError, OSError, ssl.SSLError):
        pass
    finally:
        try:
            tls_writer.close()
        except OSError:
            pass


async def _upgrade_to_tls_server(reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                                  ssl_context: ssl.SSLContext) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Upgrade an already-connected plaintext asyncio stream pair to TLS, server side.

    ``loop.start_tls`` wires the *new* protocol up to the new TLS transport itself (calling its
    ``connection_made``) -- the protocol passed in must be the one that should receive decrypted
    data going forward, not whatever was driving the old plaintext transport.
    """
    loop = asyncio.get_event_loop()
    new_reader = asyncio.StreamReader(loop=loop)
    new_protocol = _TlsStreamReaderProtocol(new_reader, loop=loop)
    new_transport = await loop.start_tls(
        writer.transport, new_protocol, ssl_context, server_side=True,
    )
    new_writer = asyncio.StreamWriter(new_transport, new_protocol, new_reader, loop)
    return new_reader, new_writer


async def _serve_decrypted_requests(ctx: RunContext, host: str, port: int,
                                     reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    while True:
        raw = await _read_headers(reader)
        if not raw:
            return
        start_line, headers = _parse_headers(raw)
        prefetched = raw.partition(b"\r\n\r\n")[2]
        method, path, _ = start_line.split(" ", 2)
        body = await _read_body(reader, prefetched, headers)
        url = f"https://{host}{path}"
        await proxy_one_request(ctx, host, port, True, method, path, url, headers, body, writer)


async def _tunnel_opaque(host: str, port: int, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                          prefetched: bytes) -> None:
    """Splice raw bytes between the client and the real server -- never decrypted, never recorded."""
    try:
        upstream_reader, upstream_writer = await asyncio.open_connection(host, port)
    except OSError:
        writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
        await writer.drain()
        return

    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
    await writer.drain()
    if prefetched:
        upstream_writer.write(prefetched)
        await upstream_writer.drain()

    async def pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
        try:
            while True:
                chunk = await src.read(65536)
                if not chunk:
                    break
                dst.write(chunk)
                await dst.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            try:
                dst.close()
            except OSError:
                pass

    await asyncio.gather(
        pipe(reader, upstream_writer),
        pipe(upstream_reader, writer),
        return_exceptions=True,
    )
