"""Tests for agent_chaos.claude's routing and CLI-parsing logic.

No real Anthropic API key or claude CLI needed: subprocess.run and the two backends are mocked,
so this runs the same in CI as locally.
"""
import json
import shutil
import subprocess

import pytest

from agent_chaos import claude


def test_auto_uses_api_when_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(claude, "_call_api", lambda prompt, **kw: "from-api")
    assert claude.call_claude("hi") == "from-api"


def test_auto_falls_back_to_cli_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(claude, "_call_cli", lambda prompt, **kw: "from-cli")
    assert claude.call_claude("hi") == "from-cli"


def test_prefer_cli_overrides_key_being_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(claude, "_call_cli", lambda prompt, **kw: "from-cli")
    assert claude.call_claude("hi", prefer="cli") == "from-cli"


def test_prefer_api_without_key_raises():
    with pytest.raises(claude.ClaudeUnavailable):
        claude._call_api("hi", model=claude.DEFAULT_MODEL, system=None)


def test_invalid_prefer_raises_value_error():
    with pytest.raises(ValueError):
        claude.call_claude("hi", prefer="bogus")


def test_cli_raises_when_binary_missing(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(claude.ClaudeUnavailable, match="claude.*PATH"):
        claude._call_cli("hi", model=claude.DEFAULT_MODEL, system=None, timeout=5)


def test_cli_parses_json_result(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(cmd, **kwargs):
        assert cmd[0] == "/usr/bin/claude"
        assert "--output-format" in cmd and "json" in cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"result": "hello", "is_error": False}), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert claude._call_cli("hi", model=claude.DEFAULT_MODEL, system=None, timeout=5) == "hello"


def test_cli_includes_system_prompt_flag(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"result": "ok", "is_error": False}), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    claude._call_cli("hi", model=claude.DEFAULT_MODEL, system="be terse", timeout=5)
    assert "--append-system-prompt" in captured["cmd"] and "be terse" in captured["cmd"]


def test_cli_raises_on_nonzero_exit(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="not logged in")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(claude.ClaudeUnavailable, match="not logged in"):
        claude._call_cli("hi", model=claude.DEFAULT_MODEL, system=None, timeout=5)


def test_cli_raises_on_is_error_true(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"result": "boom", "is_error": True}), stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(claude.ClaudeUnavailable):
        claude._call_cli("hi", model=claude.DEFAULT_MODEL, system=None, timeout=5)


def test_cli_raises_on_non_json_output(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, stdout="not json", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(claude.ClaudeUnavailable):
        claude._call_cli("hi", model=claude.DEFAULT_MODEL, system=None, timeout=5)


def test_cli_raises_on_timeout(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/claude")

    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 5))

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(claude.ClaudeUnavailable, match="timed out"):
        claude._call_cli("hi", model=claude.DEFAULT_MODEL, system=None, timeout=5)


def test_call_claude_is_a_plain_wrappable_callable():
    """The whole point: it's just a sync callable, so ctx.wrap/fault injection works for free."""
    from agent_chaos import Kind, RunContext, ToolTimeout, faults

    ctx = RunContext(0, [faults.Timeout("model=claude")])
    tool = ctx.wrap("claude", lambda prompt: "unreachable", kind=Kind.MODEL_CALL)
    with pytest.raises(ToolTimeout):
        tool("hi")
