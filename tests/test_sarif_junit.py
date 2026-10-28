import json
import xml.etree.ElementTree as ET

from agent_chaos import Scenario, run_all
from agent_chaos.report import to_junit_xml, to_sarif, write_junit, write_sarif


def _summary():
    def ok(task, ctx):
        return ctx.wrap("t", lambda: 1)()

    def crashes(task, ctx):
        return ctx.wrap("t", lambda: 1)(), ctx.wrap("t", lambda: (_ for _ in ()).throw(RuntimeError("boom")))()

    scenarios = [
        Scenario("passes", ok, "x", [], [], trials=2),
        Scenario("fails", crashes, "x", [], [], trials=2),
        Scenario("unsafe", ok, "x", [], [__import__("agent_chaos").oracles.forbidden_action("t")], trials=1),
    ]
    return run_all(scenarios)


def test_sarif_has_a_result_per_failing_scenario():
    summary = _summary()
    sarif = to_sarif(summary, target_spec="my_scenarios.py")
    assert sarif["version"] == "2.1.0"
    results = sarif["runs"][0]["results"]
    rule_ids = {r["ruleId"] for r in results}
    assert "fails" in rule_ids and "unsafe" in rule_ids and "passes" not in rule_ids
    levels = {r["ruleId"]: r["level"] for r in results}
    assert levels["unsafe"] == "error" and levels["fails"] == "warning"
    assert json.dumps(sarif)  # fully JSON-serializable


def test_write_sarif_writes_valid_json(tmp_path):
    out = tmp_path / "r.sarif"
    write_sarif(_summary(), out)
    data = json.loads(out.read_text())
    assert data["runs"][0]["tool"]["driver"]["name"] == "agent-chaos"


def test_junit_counts_failures_and_errors():
    summary = _summary()
    suite = to_junit_xml(summary)
    assert suite.attrib["tests"] == "3"
    assert suite.attrib["failures"] == "1"
    assert suite.attrib["errors"] == "1"
    cases = suite.findall("testcase")
    assert len(cases) == 3
    failing = next(c for c in cases if c.attrib["name"] == "fails")
    assert failing.find("failure") is not None
    unsafe = next(c for c in cases if c.attrib["name"] == "unsafe")
    assert unsafe.find("error") is not None
    passing = next(c for c in cases if c.attrib["name"] == "passes")
    assert passing.find("failure") is None and passing.find("error") is None


def test_write_junit_produces_parseable_xml(tmp_path):
    out = tmp_path / "r.xml"
    write_junit(_summary(), out)
    tree = ET.parse(out)
    assert tree.getroot().tag == "testsuite"


def test_cli_run_writes_sarif_and_junit(tmp_path):
    scenario_file = tmp_path / "s.py"
    scenario_file.write_text(
        "from agent_chaos import Scenario\n"
        "def ok(task, ctx):\n"
        "    return ctx.wrap('t', lambda: 1)()\n"
        "SCENARIOS = [Scenario('s', ok, 'x', [], [], trials=1)]\n"
    )
    from agent_chaos.cli import main

    sarif_out = tmp_path / "r.sarif"
    junit_out = tmp_path / "r.xml"
    assert main(["run", str(scenario_file), "--sarif", str(sarif_out), "--junit", str(junit_out)]) == 0
    assert json.loads(sarif_out.read_text())["version"] == "2.1.0"
    assert ET.parse(junit_out).getroot().tag == "testsuite"
