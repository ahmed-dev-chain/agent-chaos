import pytest

from agent_chaos import (
    Kind,
    Level,
    RunContext,
    Scenario,
    ToolError,
    ToolTimeout,
    faults,
    oracles,
    policies,
    run_scenario,
)
from agent_chaos.core.errors import StepLimitExceeded
from agent_chaos.scoring import wilson_interval


def make_ctx(fault_list, seed=1):
    return RunContext(seed, fault_list)


def test_no_faults_passthrough():
    ctx = make_ctx([])
    tool = ctx.wrap("add", lambda a, b: a + b)
    assert tool(1, 2) == 3
    assert ctx.events[0].executed and ctx.events[0].args == {"a": 1, "b": 2}


def test_timeout_does_not_execute_real_call():
    ctx = make_ctx([faults.Timeout("tool=t")])
    ran = []
    tool = ctx.wrap("t", lambda: ran.append(1))
    with pytest.raises(ToolTimeout):
        tool()
    assert not ran and not ctx.events[0].executed and ctx.clock_ms == 30_000


def test_partial_success_executes_then_raises():
    ctx = make_ctx([faults.PartialSuccess("tool=pay")])
    ran = []
    tool = ctx.wrap("pay", lambda: ran.append(1), side_effect=True)
    with pytest.raises(ToolTimeout):
        tool()
    assert ran == [1] and ctx.events[0].executed


def test_error_status_and_rate_limit():
    ctx = make_ctx([faults.RateLimit("tool=t")])
    with pytest.raises(ToolError) as info:
        ctx.wrap("t", lambda: 1)()
    assert info.value.status == 429


def test_malformed_output_truncates_dict():
    ctx = make_ctx([faults.MalformedOutput("tool=t")])
    out = ctx.wrap("t", lambda: {"a": 1, "b": 2, "c": 3, "d": 4})()
    assert list(out) == ["a", "b"]


def test_injection_appends_payload():
    ctx = make_ctx([faults.IndirectInjection("tool=t", payload="EVIL")])
    out = ctx.wrap("t", lambda: {"note": "hi", "n": 1})()
    assert out["note"].endswith("EVIL") and out["n"] == 1


def test_duplicate_delivery_runs_twice():
    ctx = make_ctx([faults.DuplicateDelivery("tool=t")])
    ran = []
    ctx.wrap("t", lambda: ran.append(1) or len(ran))()
    assert ran == [1, 1]


def test_on_call_policy_only_fires_on_nth():
    ctx = make_ctx([faults.ErrorStatus("tool=t", policies.OnCall(2))])
    tool = ctx.wrap("t", lambda: "ok")
    assert tool() == "ok"
    with pytest.raises(ToolError):
        tool()
    assert tool() == "ok"


def test_same_seed_same_decisions():
    def run(seed):
        ctx = make_ctx([faults.ErrorStatus("tool=t", policies.Probability(0.5))], seed)
        tool = ctx.wrap("t", lambda: 1)
        out = []
        for _ in range(30):
            try:
                tool()
                out.append(0)
            except ToolError:
                out.append(1)
        return out

    assert run(7) == run(7)
    assert run(7) != run(8)


def test_where_selector_validation():
    with pytest.raises(ValueError):
        make_ctx([faults.Timeout("nonsense")]).wrap("t", lambda: 1)()


def test_http_kind_selector():
    ctx = make_ctx([faults.ErrorStatus("http=api.*")])
    ctx.call(Kind.TOOL_CALL, "api.x", lambda: 1)  # tool kind: not matched
    with pytest.raises(ToolError):
        ctx.call(Kind.HTTP, "api.x", lambda: 1)


def test_step_cap_detects_loops():
    ctx = RunContext(0, [], hard_step_cap=5)
    tool = ctx.wrap("t", lambda: 1)
    with pytest.raises(StepLimitExceeded):
        for _ in range(10):
            tool()


def test_oracles_levels():
    ctx = make_ctx([])
    pay = ctx.wrap("pay", lambda amount: 1, side_effect=True)
    pay(amount=5)
    pay(amount=5)
    assert oracles.no_duplicate_side_effect("pay")(ctx, None).level == Level.UNSAFE
    assert oracles.forbidden_action("pay", amount=5)(ctx, None).level == Level.UNSAFE
    assert oracles.forbidden_action("pay", amount=6)(ctx, None) is None
    assert oracles.max_steps(1)(ctx, None).level == Level.FAILED
    assert oracles.result_check(lambda r: r == 1)(ctx, 2).level == Level.FAILED


def test_idempotency_key_dedupes_effects():
    ctx = make_ctx([])
    pay = ctx.wrap("pay", lambda amount, idempotency_key=None: 1, side_effect=True)
    pay(amount=5, idempotency_key="k")
    pay(amount=5, idempotency_key="k")
    assert oracles.no_duplicate_side_effect("pay")(ctx, None) is None


def test_latency_and_cost_are_degraded_not_failed():
    ctx = make_ctx([faults.Timeout("tool=t", ms=5000)])
    try:
        ctx.wrap("t", lambda: 1)()
    except ToolTimeout:
        pass
    ctx.add_cost(2.0)
    assert oracles.max_latency_ms(1000)(ctx, None).level == Level.DEGRADED
    assert oracles.max_cost(1.0)(ctx, None).level == Level.DEGRADED


def test_run_scenario_counts_crashes_as_failed():
    def target(task, ctx):
        return ctx.wrap("t", lambda: 1)()

    sc = Scenario("s", target, "x", [faults.Timeout("tool=t")], [], trials=5)
    res = run_scenario(sc)
    assert res.count(Level.FAILED) == 5 and res.rate == 0.0


def test_wilson_interval_bounds():
    lo, hi = wilson_interval(20, 20)
    assert 0.8 < lo < 1.0 and hi == pytest.approx(1.0)
    assert wilson_interval(0, 0) == (0.0, 1.0)
