import importlib.util
import pathlib
import sys

from agent_chaos import run_all
from agent_chaos.cli import main

EXAMPLE = pathlib.Path(__file__).parent.parent / "examples" / "support_agent.py"


def load():
    spec = importlib.util.spec_from_file_location("support_agent", EXAMPLE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["support_agent"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_hardened_beats_naive():
    mod = load()
    naive = run_all(mod.NAIVE)
    hardened = run_all(mod.HARDENED)
    assert hardened.score == 100.0 and hardened.gate_passed
    assert naive.score < 60 and naive.unsafe_count > 0 and not naive.gate_passed


def test_cli_exit_codes_and_replay(capsys, tmp_path):
    assert main(["run", str(EXAMPLE) + ":HARDENED", "--html", str(tmp_path), "--json", str(tmp_path / "r.json")]) == 0
    assert (tmp_path / "index.html").exists() and (tmp_path / "r.json").exists()
    assert main(["run", str(EXAMPLE) + ":NAIVE"]) == 1
    assert main(["replay", str(EXAMPLE) + ":NAIVE", "--scenario", "prompt_injection", "--trial", "0"]) == 0
    out = capsys.readouterr().out
    assert "forbidden action" in out and "issue_refund" in out


def test_replay_is_deterministic():
    mod = load()
    from agent_chaos import run_trial

    sc = next(s for s in mod.NAIVE if s.name == "tool_timeout")
    a, b = run_trial(sc, 3), run_trial(sc, 3)
    assert a.trace == b.trace and a.verdict == b.verdict
