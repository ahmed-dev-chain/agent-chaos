import ast

import pytest

from agent_chaos.cli import main
from agent_chaos.scaffold import detect_framework, render_template


def test_detect_framework_defaults_to_plain():
    # none of langgraph/crewai/langchain_core/agents is a project dependency
    assert detect_framework() == "plain"


def test_openai_agents_fingerprint_rejects_unrelated_module(monkeypatch):
    import sys
    import types

    from agent_chaos import scaffold

    fake = types.ModuleType("agents")  # no function_tool/Agent: an unrelated package named "agents"
    monkeypatch.setitem(sys.modules, "agents", fake)
    assert scaffold._has_openai_agents_sdk() is False


@pytest.mark.parametrize("framework", ["plain", "langchain", "langgraph", "crewai", "openai_agents"])
def test_render_template_is_valid_python_with_scenarios(framework):
    src = render_template(framework, "chaos_scenarios.py")
    tree = ast.parse(src)
    assigned = {t.id for node in ast.walk(tree) if isinstance(node, ast.Assign)
                for t in node.targets if isinstance(t, ast.Name)}
    assert "SCENARIOS" in assigned
    assert framework in src


def test_cli_init_writes_file(tmp_path):
    out = tmp_path / "chaos_scenarios.py"
    assert main(["init", "--out", str(out), "--framework", "plain"]) == 0
    assert out.exists()
    ast.parse(out.read_text())


def test_cli_init_refuses_to_overwrite_without_force(tmp_path):
    out = tmp_path / "chaos_scenarios.py"
    assert main(["init", "--out", str(out)]) == 0
    with pytest.raises(SystemExit):
        main(["init", "--out", str(out)])
    assert main(["init", "--out", str(out), "--force"]) == 0


def test_generated_plain_scenario_actually_runs(tmp_path):
    out = tmp_path / "chaos_scenarios.py"
    main(["init", "--out", str(out), "--framework", "plain"])
    assert main(["run", str(out), "--trials", "3"]) in (0, 1)  # just needs to execute, not crash
