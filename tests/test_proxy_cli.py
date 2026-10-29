"""Tests for the ``chaos proxy`` CLI command: argv splitting on ``--``, and the proxy/oracle wiring
(with the launched subprocess mocked -- the real proxy mechanics are covered by
tests/test_proxy.py and tests/test_proxy_connect.py, and verified by hand against real curl/httpbin
traffic per the plan).
"""
from unittest.mock import patch

import pytest

cryptography = pytest.importorskip("cryptography")

from agent_chaos.cli import main  # noqa: E402


def _write_scenario(tmp_path, *, allow_hosts=(), faults_expr="[]", oracles_expr="[]"):
    scenario_file = tmp_path / "s.py"
    scenario_file.write_text(
        "from agent_chaos import Scenario, faults, oracles\n"
        "def noop(task, ctx):\n"
        "    pass\n"
        f"SCENARIOS = [Scenario('s', noop, 'x', faults={faults_expr}, oracles={oracles_expr}, "
        f"allow_hosts={list(allow_hosts)!r})]\n"
    )
    return scenario_file


def test_argv_splits_command_on_double_dash(tmp_path):
    scenario_file = _write_scenario(tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        main(["proxy", str(scenario_file), "--scenario", "s", "--", "echo", "hi", "--flag"])
    called_command = mock_run.call_args[0][0]
    assert called_command == ["echo", "hi", "--flag"]


def test_proxy_env_is_merged_into_subprocess_env(tmp_path):
    scenario_file = _write_scenario(tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        main(["proxy", str(scenario_file), "--scenario", "s", "--", "true"])
    env = mock_run.call_args[1]["env"]
    assert "HTTP_PROXY" in env and env["HTTP_PROXY"].startswith("http://127.0.0.1:")


def test_proxy_exit_code_reflects_subprocess_failure(tmp_path):
    scenario_file = _write_scenario(tmp_path)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        code = main(["proxy", str(scenario_file), "--scenario", "s", "--", "false"])
    assert code == 1


def test_proxy_exit_code_reflects_oracle_failure(tmp_path):
    # `chaos proxy` never calls Scenario.target (the real agent is the external --command), so
    # ctx.events is always empty here (no mocked subprocess makes real traffic); max_steps(-1)
    # forces a FAILED verdict regardless, just to prove a failing oracle flips the exit code.
    scenario_file = _write_scenario(tmp_path, oracles_expr="[oracles.max_steps(-1)]")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        code = main(["proxy", str(scenario_file), "--scenario", "s", "--", "true"])
    assert code == 1


def test_proxy_without_command_raises():
    with pytest.raises(SystemExit):
        main(["proxy", "nonexistent.py", "--scenario", "s"])


def test_proxy_unknown_scenario_raises(tmp_path):
    scenario_file = _write_scenario(tmp_path)
    with pytest.raises(SystemExit):
        main(["proxy", str(scenario_file), "--scenario", "nope", "--", "true"])
