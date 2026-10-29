"""Tests for HTTPS CONNECT handling: MITM-decrypt for allow-listed hosts, opaque tunnel otherwise.

The real end-to-end verification against a genuine public HTTPS endpoint (httpbin.org, with a real
upstream TLS handshake and real cert validation) was done by hand per the plan, including fault
injection and the opaque-tunnel safety boundary. These automated tests isolate the custom, risky
part of this feature -- the client-facing TLS termination and decrypted request handling -- by
mocking the upstream dial-out (``_fetch``), which is otherwise just a generic TLS client already
covered by that manual check and by Phase 2's plain-HTTP tests. The opaque-tunnel path needs no
mocking: it never terminates TLS at all, so a real local TLS server exercises it fully offline.
"""
import http.client
import json
import socket
import ssl
import threading

import pytest

cryptography = pytest.importorskip("cryptography")

from agent_chaos import RunContext, faults  # noqa: E402
from agent_chaos.intercept import proxy as proxy_module  # noqa: E402
from agent_chaos.intercept import run_proxy  # noqa: E402
from agent_chaos.intercept.proxy import ProxyResponse  # noqa: E402
from agent_chaos.intercept.proxy_connect import _get_ca  # noqa: E402


def _https_via_proxy(proxy_url, target_host, path="/", timeout=5):
    proxy_host, proxy_port = proxy_url.replace("http://", "").split(":")
    ca_path = str(_get_ca().cert_path)
    ctx = ssl.create_default_context(cafile=ca_path)
    conn = http.client.HTTPSConnection(proxy_host, int(proxy_port), context=ctx, timeout=timeout)
    conn.set_tunnel(target_host)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, body


async def _fake_fetch(host, port, method, target, headers, body, *, use_tls=False):
    assert use_tls is True
    payload = json.dumps({"host": host, "target": target}).encode()
    return ProxyResponse(200, content=payload, headers={"content-type": "application/json"})


def test_allowlisted_host_is_decrypted_and_recorded(monkeypatch):
    monkeypatch.setattr(proxy_module, "_fetch", _fake_fetch)
    ctx = RunContext(0, [])
    with run_proxy(ctx, ["testhost.example"]) as p:
        status, body = _https_via_proxy(p.url, "testhost.example", "/path")
    assert status == 200
    assert json.loads(body) == {"host": "testhost.example", "target": "/path"}
    assert len(ctx.events) == 1
    assert ctx.events[0].kind.value == "http" and ctx.events[0].executed


def test_fault_injection_works_over_decrypted_https(monkeypatch):
    monkeypatch.setattr(proxy_module, "_fetch", _fake_fetch)
    ctx = RunContext(0, [faults.ErrorStatus("http=*testhost.example", status=503)])
    with run_proxy(ctx, ["testhost.example"]) as p:
        status, _ = _https_via_proxy(p.url, "testhost.example")
    assert status == 503
    assert ctx.events[0].faults == ["error_status"]


def test_timeout_fault_over_https_drops_without_real_call(monkeypatch):
    monkeypatch.setattr(proxy_module, "_fetch", _fake_fetch)
    ctx = RunContext(0, [faults.Timeout("http=*testhost.example")])
    with run_proxy(ctx, ["testhost.example"]) as p:
        with pytest.raises((http.client.HTTPException, OSError)):
            _https_via_proxy(p.url, "testhost.example", timeout=5)
    assert not ctx.events[0].executed


def test_non_allowlisted_host_is_opaque_and_unrecorded():
    """A real local TLS server stands in for an upstream the proxy was never told to MITM. The
    proxy must tunnel it untouched -- no decryption, no Event, regardless of what's inside."""
    ca = _get_ca()
    cert_pem, key_pem = ca.leaf_for("upstream.test")

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        cert_path = Path(tmp) / "leaf.pem"
        key_path = Path(tmp) / "leaf-key.pem"
        cert_path.write_bytes(cert_pem)
        key_path.write_bytes(key_pem)
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.load_cert_chain(str(cert_path), str(key_path))

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        upstream_port = sock.getsockname()[1]

        def serve():
            conn, _ = sock.accept()
            tls = server_ctx.wrap_socket(conn, server_side=True)
            tls.recv(4096)
            tls.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
            tls.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()

        ctx = RunContext(0, [])
        # allow-list some OTHER host: upstream.test on 127.0.0.1 must still go through untouched
        with run_proxy(ctx, ["some-other-host.example"]) as p:
            status, body = _https_via_proxy_direct_port(p.url, "127.0.0.1", upstream_port, str(ca.cert_path))
        assert status == 200 and body == b"ok"
        assert len(ctx.events) == 0
        thread.join(timeout=5)


def test_connect_to_unreachable_non_allowlisted_host_returns_bad_gateway():
    """A non-allow-listed CONNECT target that's unreachable gets a clean 502, not a hang."""
    ctx = RunContext(0, [])
    with run_proxy(ctx, []) as p:
        proxy_host, proxy_port = p.url.replace("http://", "").split(":")
        unused = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        unused.bind(("127.0.0.1", 0))
        dead_port = unused.getsockname()[1]
        unused.close()  # nothing listens here: a fast, deterministic "unreachable" target

        with socket.create_connection((proxy_host, int(proxy_port)), timeout=5) as sock:
            sock.sendall(f"CONNECT 127.0.0.1:{dead_port} HTTP/1.1\r\n\r\n".encode())
            resp = sock.recv(200)
    assert b"502" in resp
    assert not ctx.events


def test_handle_exposes_ca_cert_and_env_only_when_allow_hosts_given():
    ctx = RunContext(0, [])
    with run_proxy(ctx, []) as p_no_hosts:
        assert p_no_hosts.ca_cert_path is None
        assert "SSL_CERT_FILE" not in p_no_hosts.env

    with run_proxy(ctx, ["testhost.example"]) as p_with_hosts:
        assert p_with_hosts.ca_cert_path == str(_get_ca().cert_path)
        for key in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS"):
            assert p_with_hosts.env[key] == p_with_hosts.ca_cert_path


def _https_via_proxy_direct_port(proxy_url, target_host, target_port, ca_path, timeout=5):
    proxy_host, proxy_port = proxy_url.replace("http://", "").split(":")
    ctx = ssl.create_default_context(cafile=ca_path)
    ctx.check_hostname = False  # the leaf cert's SAN is "upstream.test", not an IP
    ctx.verify_mode = ssl.CERT_NONE
    conn = http.client.HTTPSConnection(proxy_host, int(proxy_port), context=ctx, timeout=timeout)
    conn.set_tunnel(f"{target_host}:{target_port}")
    conn.request("GET", "/")
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, body
