"""Command line: ``chaos run | replay | record | faults | init``."""
from __future__ import annotations

import argparse
import importlib.util
import inspect
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .core.context import RunContext, _run_sync
from .core.events import Level
from .faults.base import FAULTS, load_plugins
from .record import save_trace
from .report import render, write_html, write_json, write_junit, write_sarif
from .runner import Scenario, run_all, run_trial
from .scaffold import detect_framework, render_template
from .shrink import shrink


def load_scenarios(spec: str) -> list[Scenario]:
    """``path/to/file.py`` (uses SCENARIOS) or ``path/to/file.py:ATTR``.

    Splits on the *last* colon, not the first, so a Windows drive letter (``C:\\...``) isn't
    mistaken for the ``:ATTR`` separator.
    """
    path, attr = spec, ""
    if ":" in spec:
        candidate_path, _, candidate_attr = spec.rpartition(":")
        if candidate_path and candidate_attr and not any(c in candidate_attr for c in "/\\"):
            path, attr = candidate_path, candidate_attr
    attr = attr or "SCENARIOS"
    file = Path(path).resolve()
    if not file.exists():
        raise SystemExit(f"chaos: file not found: {path}")
    sys.path.insert(0, str(file.parent))
    module_spec = importlib.util.spec_from_file_location(file.stem, file)
    assert module_spec and module_spec.loader
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[file.stem] = module
    module_spec.loader.exec_module(module)
    scenarios = getattr(module, attr, None)
    if not scenarios:
        raise SystemExit(f"chaos: {path} has no list named {attr}")
    return list(scenarios)


def cmd_run(args: argparse.Namespace) -> int:
    scenarios = load_scenarios(args.target)
    summary = run_all(scenarios, trials=args.trials, seed=args.seed, min_score=args.min_score)
    print(render(summary, args.target))
    if args.html:
        print("HTML report:", write_html(summary, args.html))
    if args.json:
        write_json(summary, args.json)
    if args.sarif:
        write_sarif(summary, args.sarif, args.target)
    if args.junit:
        write_junit(summary, args.junit)
    return 0 if summary.gate_passed else 1


def _print_trial(result) -> None:  # noqa: ANN001 - TrialResult, kept loose to avoid an import cycle
    print(f"scenario={result.scenario} trial={result.trial} seed={result.seed}")
    print(f"verdict: {result.verdict.level.value}  {result.verdict.reason}")
    print("trace:")
    for e in result.trace:
        faults = f"  <- {','.join(e['faults'])}" if e["faults"] else ""
        err = f"  !! {e['error']}" if e["error"] else ""
        print(f"  {e['id']:>2}. {e['name']}({json.dumps(e['args'])}){faults}{err}")


def cmd_replay(args: argparse.Namespace) -> int:
    scenarios = load_scenarios(args.target)
    match = [s for s in scenarios if s.name == args.scenario]
    if not match:
        raise SystemExit(f"chaos: no scenario named {args.scenario!r}; have {[s.name for s in scenarios]}")
    if args.seed is not None:
        match[0].seed = args.seed
    _print_trial(run_trial(match[0], args.trial))
    return 0


def cmd_shrink(args: argparse.Namespace) -> int:
    scenarios = load_scenarios(args.target)
    match = [s for s in scenarios if s.name == args.scenario]
    if not match:
        raise SystemExit(f"chaos: no scenario named {args.scenario!r}; have {[s.name for s in scenarios]}")
    try:
        shrunk = shrink(match[0], args.trial, Level(args.severity))
    except ValueError as exc:
        raise SystemExit(f"chaos: {exc}") from exc
    print(f"chaos: shrunk {len(match[0].faults)} fault(s) to {len(shrunk.faults)}:")
    for f in shrunk.faults:
        print(f"  {f!r}")
    _print_trial(run_trial(shrunk, args.trial))
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    scenarios = load_scenarios(args.target)
    match = [s for s in scenarios if s.name == args.scenario]
    if not match:
        raise SystemExit(f"chaos: no scenario named {args.scenario!r}; have {[s.name for s in scenarios]}")
    sc = match[0]
    seed = args.seed if args.seed is not None else sc.seed
    ctx = RunContext(seed, [], sc.hard_step_cap)  # no faults: record the real, unfaulted run
    result = sc.target(sc.task, ctx)
    if inspect.isawaitable(result):
        result = _run_sync(result)
    save_trace(ctx, args.out)
    print(f"chaos: recorded {len(ctx.events)} calls to {args.out}")
    print(f'       replay offline: faults=[load_replay("{args.out}")]')
    return 0


def cmd_faults(_: argparse.Namespace) -> int:
    load_plugins()
    for name, cls in sorted(FAULTS.items()):
        doc = (cls.__doc__ or "").strip().splitlines()[0] if cls.__doc__ else ""
        print(f"{name:<22} [{cls.category}] {doc}")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    out = Path(args.out)
    if out.exists() and not args.force:
        raise SystemExit(f"chaos: {out} already exists (use --force to overwrite)")
    framework = args.framework or detect_framework()
    out.write_text(render_template(framework, out.name))
    print(f"chaos: wrote {out} (detected framework: {framework})")
    print(f"       edit it, then: chaos run {out}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="chaos", description="Chaos engineering for AI agents")
    parser.add_argument("--version", action="version", version=f"agent-chaos {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run scenarios and print a resilience report")
    run.add_argument("target", help="file.py or file.py:ATTR holding a list of Scenario objects")
    run.add_argument("--trials", type=int, default=None, help="override trials per scenario")
    run.add_argument("--seed", type=int, default=None, help="override base seed")
    run.add_argument("--min-score", type=float, default=0.0, help="fail the gate below this score")
    run.add_argument("--html", metavar="DIR", help="write an HTML report to DIR")
    run.add_argument("--json", metavar="FILE", help="write a JSON report to FILE")
    run.add_argument("--sarif", metavar="FILE", help="write a SARIF 2.1.0 report to FILE")
    run.add_argument("--junit", metavar="FILE", help="write a JUnit XML report to FILE")
    run.set_defaults(func=cmd_run)

    rep = sub.add_parser("replay", help="re-run one trial exactly and print its trace")
    rep.add_argument("target")
    rep.add_argument("--scenario", required=True)
    rep.add_argument("--trial", type=int, required=True)
    rep.add_argument("--seed", type=int, default=None)
    rep.set_defaults(func=cmd_replay)

    rec = sub.add_parser("record", help="run a scenario's target with no faults and save the real trace")
    rec.add_argument("target")
    rec.add_argument("--scenario", required=True)
    rec.add_argument("--seed", type=int, default=None)
    rec.add_argument("--out", required=True, metavar="FILE", help="trace file to write (load with load_replay)")
    rec.set_defaults(func=cmd_record)

    shr = sub.add_parser("shrink", help="reduce a failing trial's faults to the smallest set that still reproduces it")
    shr.add_argument("target")
    shr.add_argument("--scenario", required=True)
    shr.add_argument("--trial", type=int, required=True)
    shr.add_argument("--severity", choices=["failed", "unsafe"], default="failed",
                      help="minimum verdict severity to preserve (default: failed)")
    shr.set_defaults(func=cmd_shrink)

    fl = sub.add_parser("faults", help="list available faults")
    fl.set_defaults(func=cmd_faults)

    init = sub.add_parser("init", help="detect the agent framework and write a starter scenario file")
    init.add_argument("--out", default="chaos_scenarios.py", help="path to write (default: chaos_scenarios.py)")
    init.add_argument("--framework", choices=["plain", "langchain", "langgraph", "crewai", "openai_agents"],
                       help="skip auto-detection and use this template")
    init.add_argument("--force", action="store_true", help="overwrite --out if it already exists")
    init.set_defaults(func=cmd_init)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
