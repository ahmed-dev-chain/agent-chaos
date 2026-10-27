import pytest

httpx = pytest.importorskip("httpx")

from agent_chaos import RunContext, faults, policies
from agent_chaos.intercept import patch_httpx


def client():
    return httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True, "x": 1, "y": 2})))


def test_passthrough_records_event():
    ctx = RunContext(0, [])
    with patch_httpx(ctx):
        r = client().get("https://api.example.com/a")
    assert r.status_code == 200 and ctx.events[0].name == "GET api.example.com"


def test_error_status_becomes_response():
    ctx = RunContext(0, [faults.ErrorStatus("http=*example.com", status=503)])
    with patch_httpx(ctx):
        r = client().get("https://api.example.com/a")
    assert r.status_code == 503


def test_timeout_becomes_read_timeout():
    ctx = RunContext(0, [faults.Timeout("http=*")])
    with patch_httpx(ctx), pytest.raises(httpx.ReadTimeout):
        client().get("https://api.example.com/a")


def test_post_is_side_effect_and_patch_is_removed():
    original = httpx.Client.send
    ctx = RunContext(0, [])
    with patch_httpx(ctx):
        client().post("https://api.example.com/pay", headers={"Idempotency-Key": "abc"})
    assert ctx.events[0].side_effect and ctx.events[0].idempotency_key == "abc"
    assert httpx.Client.send is original


def test_malformed_http_body_is_truncated():
    ctx = RunContext(0, [faults.MalformedOutput("http=*", policies.Always())])
    with patch_httpx(ctx):
        r = client().get("https://api.example.com/a")
    assert len(r.content) < len(b'{"ok":true,"x":1,"y":2}')
