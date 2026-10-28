"""Async support: RunContext.acall/awrap, async-aware scenario targets, async httpx patching.

No pytest-asyncio dependency: each test drives its own coroutine with ``asyncio.run`` from an
ordinary sync test function, matching the project's zero-runtime-dependency philosophy.
"""
import asyncio

import pytest

from agent_chaos import Kind, RunContext, Scenario, ToolTimeout, faults, oracles, policies, run_scenario


def make_ctx(fault_list, seed=1):
    return RunContext(seed, fault_list)


def test_acall_passthrough_records_event():
    ctx = make_ctx([])

    async def go():
        async def fn():
            return 42

        return await ctx.acall(Kind.MODEL_CALL, "m", fn)

    assert asyncio.run(go()) == 42
    assert ctx.events[0].executed and ctx.events[0].response == 42


def test_acall_timeout_never_awaits_real_fn():
    ctx = make_ctx([faults.Timeout("model=m")])
    ran = []

    async def go():
        async def fn():
            ran.append(1)
            return 1

        with pytest.raises(ToolTimeout):
            await ctx.acall(Kind.MODEL_CALL, "m", fn)

    asyncio.run(go())
    assert not ran and not ctx.events[0].executed


def test_acall_malformed_output_corrupts_async_result():
    ctx = make_ctx([faults.MalformedOutput("model=m")])

    async def go():
        async def fn():
            return {"a": 1, "b": 2, "c": 3, "d": 4}

        return await ctx.acall(Kind.MODEL_CALL, "m", fn)

    out = asyncio.run(go())
    assert list(out) == ["a", "b"]


def test_acall_duplicate_delivery_awaits_twice():
    ctx = make_ctx([faults.DuplicateDelivery("model=m")])
    calls = []

    async def go():
        async def fn():
            calls.append(1)
            return len(calls)

        return await ctx.acall(Kind.MODEL_CALL, "m", fn)

    out = asyncio.run(go())
    assert calls == [1, 1] and out == 2


def test_awrap_binds_args_like_wrap():
    ctx = make_ctx([])

    async def add(a, b):
        return a + b

    async def go():
        tool = ctx.awrap("add", add)
        return await tool(1, b=2)

    assert asyncio.run(go()) == 3
    assert ctx.events[0].args == {"a": 1, "b": 2}


def test_run_scenario_supports_async_target():
    async def agent(task, ctx):
        model = ctx.awrap("m", lambda: _reply(), kind=Kind.MODEL_CALL)
        return await model()

    async def _reply():
        return "ok"

    sc = Scenario("async_ok", agent, "x", [], [oracles.result_check(lambda r: r == "ok")], trials=3)
    res = run_scenario(sc)
    assert res.rate == 1.0


def test_run_scenario_async_target_with_fault_and_crash():
    async def agent(task, ctx):
        model = ctx.awrap("m", lambda: _reply(), kind=Kind.MODEL_CALL)
        reply = await model()
        return reply["missing"]  # will KeyError once refused

    async def _reply():
        return {"ok": True}

    sc = Scenario("async_refusal", agent, "x", [faults.Refusal("model=m")], [], trials=1, seed=0)
    res = run_scenario(sc)
    assert res.trials[0].verdict.level.value == "failed"


httpx = pytest.importorskip("httpx")

from agent_chaos.intercept import patch_httpx  # noqa: E402


def _async_client():
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"ok": True, "x": 1, "y": 2}))
    return httpx.AsyncClient(transport=transport)


def test_async_httpx_passthrough():
    ctx = RunContext(0, [])

    async def run():
        with patch_httpx(ctx):
            async with _async_client() as client:
                return await client.get("https://api.example.com/a")

    r = asyncio.run(run())
    assert r.status_code == 200 and ctx.events[0].name == "GET api.example.com"


def test_async_httpx_error_status_becomes_response():
    ctx = RunContext(0, [faults.ErrorStatus("http=*example.com", status=503)])

    async def run():
        with patch_httpx(ctx):
            async with _async_client() as client:
                return await client.get("https://api.example.com/a")

    r = asyncio.run(run())
    assert r.status_code == 503


def test_async_httpx_timeout_becomes_read_timeout():
    ctx = RunContext(0, [faults.Timeout("http=*")])

    async def run():
        with patch_httpx(ctx):
            async with _async_client() as client:
                await client.get("https://api.example.com/a")

    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(run())


def test_async_httpx_malformed_output_corrupts_body():
    ctx = RunContext(0, [faults.MalformedOutput("http=*", policies.Always())])

    async def run():
        with patch_httpx(ctx):
            async with _async_client() as client:
                return await client.get("https://api.example.com/a")

    r = asyncio.run(run())
    assert len(r.content) < len(b'{"ok":true,"x":1,"y":2}')


def test_sync_and_async_httpx_patches_coexist_and_restore():
    original_sync = httpx.Client.send
    original_async = httpx.AsyncClient.send
    ctx = RunContext(0, [])

    async def run():
        with patch_httpx(ctx):
            assert httpx.Client.send is not original_sync
            assert httpx.AsyncClient.send is not original_async
            async with _async_client() as client:
                await client.get("https://api.example.com/a")

    asyncio.run(run())
    assert httpx.Client.send is original_sync and httpx.AsyncClient.send is original_async
