import pytest

from agent_chaos import Scenario, faults, oracles


def agent(task, ctx):
    return ctx.wrap("t", lambda: "ok")()


def test_chaos_fixture_passes_for_resilient_agent(chaos):
    res = chaos.run(Scenario("s", agent, "x", [faults.RateLimit("tool=zzz")], [oracles.max_steps(3)], trials=5))
    chaos.assert_resilient(res, min_score=100)


def test_chaos_fixture_fails_for_fragile_agent(chaos):
    res = chaos.run(Scenario("s", agent, "x", [faults.Timeout("tool=t")], [], trials=5))
    with pytest.raises(AssertionError, match="resilience score"):
        chaos.assert_resilient(res, min_score=90)
