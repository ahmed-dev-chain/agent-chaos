"""JUnit XML output, for CI systems that consume it. stdlib only, no new dependency."""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..core.events import Level
from ..runner import RunSummary


def to_junit_xml(summary: RunSummary) -> ET.Element:
    suite = ET.Element(
        "testsuite",
        name="agent-chaos",
        tests=str(len(summary.results)),
        failures=str(sum(1 for r in summary.results if r.count(Level.FAILED))),
        errors=str(sum(1 for r in summary.results if r.count(Level.UNSAFE))),
    )
    for r in summary.results:
        case = ET.SubElement(suite, "testcase", name=r.scenario.name, classname="agent_chaos")
        bad = r.first_failure
        if bad and bad.verdict.level == Level.UNSAFE:
            ET.SubElement(case, "error", message=bad.verdict.reason)
        elif bad:
            ET.SubElement(case, "failure", message=bad.verdict.reason)
    return suite


def write_junit(summary: RunSummary, path: str | Path) -> Path:
    p = Path(path)
    ET.ElementTree(to_junit_xml(summary)).write(p, encoding="utf-8", xml_declaration=True)
    return p
