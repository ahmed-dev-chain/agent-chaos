"""Tests for the plain-HTTP transparent proxy, against a local throwaway HTTP server (no real
internet needed, so these stay fast and offline-safe in CI). The manual verification against real
internet traffic (curl -x ... http://example.com, with real fault injection) was done by hand per
the plan and is not repeated here as an automated test.
"""
import http.server
import json
import threading
import urllib.error
import urllib.request

import pytest

from agent_chaos import RunContext, faults, policies
from agent_chaos.intercept import run_proxy


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence the default stderr access log
        pass

    def do_GET(self):
        body = json.dumps({"ok": True, "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")


@pytest.fixture
def local_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=5)


def _open(proxy_url, target_url, method="GET", timeout=5):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy_url}))
    req = urllib.request.Request(target_url, method=method)
    return opener.open(req, timeout=timeout)


def test_passthrough_records_event(local_server):
    ctx = RunContext(0, [])
    with run_proxy(ctx, []) as p:
        resp = _open(p.url, local_server + "/a")
        assert resp.status == 200
        assert json.loads(resp.read())["path"] == "/a"
    assert ctx.events[0].kind.value == "http" and ctx.events[0].executed


def test_error_status_fault_returns_injected_status(local_server):
    ctx = RunContext(0, [faults.ErrorStatus("http=*127.0.0.1*", status=503)])
    with run_proxy(ctx, []) as p:
        with pytest.raises(urllib.error.HTTPError) as info:
            _open(p.url, local_server + "/a")
        assert info.value.code == 503
    assert ctx.events[0].faults == ["error_status"]


def test_timeout_fault_drops_the_connection(local_server):
    ctx = RunContext(0, [faults.Timeout("http=*127.0.0.1*")])
    with run_proxy(ctx, []) as p:
        # the proxy closes without responding; urllib surfaces that as either a URLError or a
        # ConnectionError (http.client.RemoteDisconnected), depending on exactly when it closes
        with pytest.raises((urllib.error.URLError, ConnectionError)):
            _open(p.url, local_server + "/a", timeout=5)
    assert not ctx.events[0].executed


def test_malformed_output_truncates_body(local_server):
    ctx = RunContext(0, [faults.MalformedOutput("http=*127.0.0.1*", policies.Always())])
    with run_proxy(ctx, []) as p:
        resp = _open(p.url, local_server + "/a")
        body = resp.read()
    full = json.dumps({"ok": True, "path": "/a"}).encode()
    assert len(body) < len(full)


def test_post_is_recorded_as_side_effect(local_server):
    ctx = RunContext(0, [])
    with run_proxy(ctx, []) as p:
        resp = _open(p.url, local_server + "/b", method="POST")
        assert resp.status == 200
    assert ctx.events[0].side_effect is True
