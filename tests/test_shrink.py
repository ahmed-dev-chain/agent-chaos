import pytest

from agent_chaos import Level, Scenario, faults, oracles, policies, shrink
from agent_chaos.cli import main


def target(task, ctx):
    return ctx.wrap("t", lambda: 1)()


def test_shrink_reduces_to_the_one_fault_that_matters():
    # Only the RateLimit fault (which never lets the call through) can fail this scenario;
    # the other two never fire against "t" at all, so they should all be dropped.
    sc = Scenario(
        "s", target, "x",
        faults=[
            faults.Timeout("tool=other", policies.Always()),
            faults.ErrorStatus("tool=t", policies.Always()),
            faults.MalformedOutput("tool=other", policies.Always()),
        ],
        oracles=[oracles.max_steps(100)],
        trials=1, seed=0,
    )
    shrunk = shrink(sc, 0)
    assert len(shrunk.faults) == 1
    assert shrunk.faults[0].name == "error_status"


def test_shrink_raises_when_trial_does_not_reproduce():
    sc = Scenario("s", target, "x", faults=[], oracles=[], trials=1, seed=0)
    with pytest.raises(ValueError):
        shrink(sc, 0, Level.FAILED)


def test_shrink_preserves_unsafe_severity_specifically():
    from agent_chaos import ToolTimeout

    def naive_retry_target(task, ctx):
        pay = ctx.wrap("pay", lambda: 1, side_effect=True)
        try:
            pay()
        except ToolTimeout:
            pay()  # blind retry: unsafe if the first call actually succeeded

    sc = Scenario(
        "s", naive_retry_target, "x",
        faults=[
            faults.Timeout("tool=other", policies.Always()),  # never fires: should be dropped
            faults.PartialSuccess("tool=pay", policies.OnCall(1)),  # fires once; the retry succeeds
        ],
        oracles=[oracles.no_duplicate_side_effect("pay")],
        trials=1, seed=0,
    )
    shrunk = shrink(sc, 0, Level.UNSAFE)
    assert len(shrunk.faults) == 1
    assert shrunk.faults[0].name == "partial_success"


def test_cli_shrink_runs_end_to_end(tmp_path, capsys):
    scenario_file = tmp_path / "s.py"
    scenario_file.write_text(
        "from agent_chaos import Scenario, faults, policies\n"
        "def target(task, ctx):\n"
        "    return ctx.wrap('t', lambda: 1)()\n"
        "SCENARIOS = [Scenario('s', target, 'x', "
        "faults=[faults.ErrorStatus('tool=t', policies.Always())], oracles=[], trials=1, seed=0)]\n"
    )
    assert main(["shrink", str(scenario_file), "--scenario", "s", "--trial", "0"]) == 0
    out = capsys.readouterr().out
    assert "shrunk" in out and "error_status" in out
