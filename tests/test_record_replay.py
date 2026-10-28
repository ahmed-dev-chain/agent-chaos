import asyncio
import json

import pytest

from agent_chaos import (
    Kind,
    ReplayedError,
    ReplayMismatch,
    RunContext,
    Scenario,
    ToolError,
    load_replay,
    run_scenario,
    save_trace,
)
from agent_chaos.cli import main


def test_record_then_replay_reproduces_result_with_no_real_calls(tmp_path):
    calls = []

    def target(task, ctx):
        search = ctx.wrap("search", lambda q: calls.append(q) or {"result": q})
        return search(q=task)

    ctx = RunContext(0, [])
    real_result = target("hello", ctx)
    path = tmp_path / "trace.json"
    save_trace(ctx, path)
    assert calls == ["hello"]

    replay_fault = load_replay(path)
    ctx2 = RunContext(99, [replay_fault])  # different seed: replay must not care
    replayed_result = target("hello", ctx2)

    assert replayed_result == real_result
    assert calls == ["hello"]  # unchanged: the real function was never called again
    assert ctx2.events[0].executed is False  # real call was skipped


def test_replay_preserves_async_targets(tmp_path):
    async def target(task, ctx):
        model = ctx.awrap("m", lambda: _reply(task), kind=Kind.MODEL_CALL)
        return await model()

    async def _reply(task):
        return {"answer": task}

    ctx = RunContext(0, [])
    real_result = asyncio.run(target("x", ctx))
    path = tmp_path / "trace.json"
    save_trace(ctx, path)

    ctx2 = RunContext(0, [load_replay(path)])
    replayed = asyncio.run(target("x", ctx2))
    assert replayed == real_result


def test_replay_mismatch_on_diverged_call_sequence(tmp_path):
    def recorder_target(task, ctx):
        ctx.wrap("a", lambda: 1)()
        ctx.wrap("b", lambda: 2)()

    ctx = RunContext(0, [])
    recorder_target("x", ctx)
    path = tmp_path / "trace.json"
    save_trace(ctx, path)

    def diverged_target(task, ctx):
        ctx.wrap("a", lambda: 1)()
        ctx.wrap("c", lambda: 3)()  # diverges from the recording's "b"

    ctx2 = RunContext(0, [load_replay(path)])
    with pytest.raises(ReplayMismatch):
        diverged_target("x", ctx2)


def test_replay_mismatch_when_target_makes_more_calls(tmp_path):
    def recorder_target(task, ctx):
        ctx.wrap("a", lambda: 1)()

    ctx = RunContext(0, [])
    recorder_target("x", ctx)
    path = tmp_path / "trace.json"
    save_trace(ctx, path)

    def longer_target(task, ctx):
        ctx.wrap("a", lambda: 1)()
        ctx.wrap("a", lambda: 1)()  # a second call to "a": no recording for index 2

    ctx2 = RunContext(0, [load_replay(path)])
    with pytest.raises(ReplayMismatch):
        longer_target("x", ctx2)


def test_replay_works_identically_across_many_trials(tmp_path):
    """Regression test: ReplayFault must not drain across trials sharing the same Scenario."""

    def target(task, ctx):
        return ctx.wrap("search", lambda: {"result": task})()

    ctx = RunContext(0, [])
    target("hello", ctx)
    path = tmp_path / "trace.json"
    save_trace(ctx, path)

    sc = Scenario("replayed", target, "hello", [load_replay(path)], [], trials=10)
    res = run_scenario(sc)
    assert res.rate == 1.0
    assert all(t.result == {"result": "hello"} for t in res.trials)


def test_replay_reconstructs_recorded_errors_as_replayed_error(tmp_path):
    def erroring_target(task, ctx):
        ctx.wrap("a", lambda: (_ for _ in ()).throw(ToolError(500, "boom")))()

    ctx = RunContext(0, [])
    with pytest.raises(ToolError):
        erroring_target("x", ctx)
    path = tmp_path / "trace.json"
    save_trace(ctx, path)

    ctx2 = RunContext(0, [load_replay(path)])
    with pytest.raises(ReplayedError):
        erroring_target("x", ctx2)


def test_cli_record_writes_valid_trace(tmp_path):
    scenario_file = tmp_path / "scenarios.py"
    scenario_file.write_text(
        "from agent_chaos import Scenario\n"
        "def my_agent(task, ctx):\n"
        "    return ctx.wrap('search', lambda: {'ok': True})()\n"
        "SCENARIOS = [Scenario('s', my_agent, 'task', [], [], trials=1)]\n"
    )
    out = tmp_path / "trace.json"
    assert main(["record", str(scenario_file), "--scenario", "s", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert len(data) == 1 and data[0]["name"] == "search" and data[0]["executed"]


def test_replay_fault_ignores_fault_category_passthrough():
    from agent_chaos.faults.base import FAULTS

    assert "replay" in FAULTS
    assert FAULTS["replay"].category == "replay"
