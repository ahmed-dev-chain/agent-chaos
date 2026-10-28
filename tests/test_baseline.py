from agent_chaos import Scenario, compare_baseline, oracles, run_all, save_baseline
from agent_chaos.cli import main


def _scenario(name, ok_trials, oracles_list=()):
    calls = {"n": 0}

    def target(task, ctx):
        calls["n"] += 1
        return ctx.wrap("t", lambda: 1)()

    return Scenario(name, target, "x", [], list(oracles_list), trials=ok_trials, seed=0)


def test_save_and_compare_roundtrip_no_regression(tmp_path):
    path = tmp_path / "baseline.json"
    summary = run_all([_scenario("s", 2)])
    save_baseline(summary, path)
    diffs = compare_baseline(summary, path)
    assert len(diffs) == 1 and diffs[0].baseline_rate == 1.0 and not diffs[0].regressed


def test_compare_flags_rate_drop_as_regression(tmp_path):
    path = tmp_path / "baseline.json"
    good = run_all([_scenario("s", 2)])
    save_baseline(good, path)

    def flaky_target(task, ctx):
        tool = ctx.wrap("t", lambda: 1)
        if ctx.rng.random() < 0.9:
            raise ValueError("boom")
        return tool()

    sc = Scenario("s", flaky_target, "x", [], [], trials=5, seed=0)
    worse = run_all([sc])
    diffs = compare_baseline(worse, path)
    assert diffs[0].regressed


def test_compare_flags_new_unsafe_as_regression(tmp_path):
    path = tmp_path / "baseline.json"
    good = run_all([_scenario("s", 2)])
    save_baseline(good, path)

    unsafe_sc = _scenario("s", 2, [oracles.forbidden_action("t")])
    unsafe_summary = run_all([unsafe_sc])
    diffs = compare_baseline(unsafe_summary, path)
    assert diffs[0].regressed


def test_compare_unknown_scenario_has_no_baseline(tmp_path):
    path = tmp_path / "baseline.json"
    save_baseline(run_all([_scenario("a", 2)]), path)
    diffs = compare_baseline(run_all([_scenario("b", 2)]), path)
    assert diffs[0].baseline_rate is None and not diffs[0].regressed


def test_cli_update_baseline_writes_file_and_does_not_fail(tmp_path):
    scenario_file = tmp_path / "s.py"
    scenario_file.write_text(
        "from agent_chaos import Scenario\n"
        "def ok(task, ctx):\n"
        "    return ctx.wrap('t', lambda: 1)()\n"
        "SCENARIOS = [Scenario('s', ok, 'x', [], [], trials=2)]\n"
    )
    baseline_file = tmp_path / "baseline.json"
    assert main(["run", str(scenario_file), "--baseline", str(baseline_file), "--update-baseline"]) == 0
    assert baseline_file.exists()


def test_cli_baseline_regression_fails_gate(tmp_path, capsys):
    scenario_file = tmp_path / "s.py"
    scenario_file.write_text(
        "from agent_chaos import Scenario, oracles\n"
        "def ok(task, ctx):\n"
        "    return ctx.wrap('t', lambda: 1)()\n"
        "SCENARIOS = [Scenario('s', ok, 'x', [], [], trials=2)]\n"
    )
    baseline_file = tmp_path / "baseline.json"
    main(["run", str(scenario_file), "--baseline", str(baseline_file), "--update-baseline"])

    unsafe_file = tmp_path / "s2.py"
    unsafe_file.write_text(
        "from agent_chaos import Scenario, oracles\n"
        "def ok(task, ctx):\n"
        "    return ctx.wrap('t', lambda: 1)()\n"
        "SCENARIOS = [Scenario('s', ok, 'x', [], [oracles.forbidden_action('t')], trials=2)]\n"
    )
    assert main(["run", str(unsafe_file), "--baseline", str(baseline_file)]) == 1
    assert "REGRESSED" in capsys.readouterr().out
