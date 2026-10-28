"""SARIF 2.1.0 output, for GitHub code scanning and other SARIF-consuming tools."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import __version__
from ..core.events import Level
from ..runner import RunSummary

_LEVEL = {Level.UNSAFE: "error", Level.FAILED: "warning"}


def to_sarif(summary: RunSummary, target_spec: str = "") -> dict[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    results = []
    for r in summary.results:
        rules[r.scenario.name] = {
            "id": r.scenario.name,
            "shortDescription": {"text": f"agent-chaos scenario: {r.scenario.name}"},
        }
        bad = r.first_failure
        if bad:
            results.append({
                "ruleId": r.scenario.name,
                "level": _LEVEL.get(bad.verdict.level, "warning"),
                "message": {"text": bad.verdict.reason},
                "locations": [{
                    "physicalLocation": {
                        "artifactLocation": {"uri": target_spec or "scenario"},
                        "region": {"startLine": 1},
                    }
                }],
            })
    return {
        "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {"name": "agent-chaos", "version": __version__, "rules": list(rules.values())}},
            "results": results,
        }],
    }


def write_sarif(summary: RunSummary, path: str | Path, target_spec: str = "") -> Path:
    p = Path(path)
    p.write_text(json.dumps(to_sarif(summary, target_spec), indent=2))
    return p
