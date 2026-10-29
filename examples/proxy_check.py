"""Demo: fault-test a non-Python agent (here, curl) through the transparent proxy.

    pip install -e ".[proxy]"
    chaos run examples/proxy_check.py

curl isn't Python code agent-chaos can wrap directly with ``ctx.wrap`` -- it's a completely
separate process. ``run_proxy`` makes its HTTPS traffic fault-testable anyway: the Scenario target
below just launches curl inside ``with run_proxy(ctx, allow_hosts)``, same as you'd launch a Node
agent, a compiled binary, or anything else.

Needs real internet access (hits https://httpbin.org) and a ``curl`` binary on PATH, so this isn't
part of the automated test suite or the CI gate -- see ``examples/support_agent.py`` for the
zero-dependency, offline demo. Expect the score to land well below 100: plain curl has no retry
logic, so an injected connection drop just fails the trial outright -- the same "works until
something breaks" lesson as the Python example, proved here against a real external process.
"""
from __future__ import annotations

import os
import subprocess
import sys

from agent_chaos import RunContext, Scenario, faults, oracles, policies
from agent_chaos.intercept import run_proxy

TASK = "fetch https://httpbin.org/get"
ALLOW_HOSTS = ["httpbin.org"]


def curl_agent(task: str, ctx: RunContext) -> str:
    with run_proxy(ctx, ALLOW_HOSTS) as p:
        cmd = ["curl", "-s", "-x", p.url]
        if p.ca_cert_path:
            cmd += ["--cacert", p.ca_cert_path]
        cmd += ["-o", os.devnull, "-w", "%{http_code}", "https://httpbin.org/get"]
        if sys.platform == "win32":
            # curl's Windows/Schannel backend fails local, non-CA-issued certs on a revocation
            # check it can't perform (no CRL/OCSP for a private CA); curl's OpenSSL-backed builds
            # elsewhere don't have or need this flag.
            cmd.append("--ssl-no-revoke")
        result = subprocess.run(cmd, env={**os.environ, **p.env}, capture_output=True, text=True, timeout=15)
    return result.stdout.strip()


SCENARIOS = [
    Scenario(
        "curl_timeout",
        curl_agent, TASK,
        faults=[faults.Timeout("http=*httpbin.org", policies.Probability(0.5))],
        oracles=[oracles.max_steps(5), oracles.result_check(lambda code: code == "200", "curl_got_a_real_response")],
        allow_hosts=ALLOW_HOSTS,
        trials=10,
    ),
]
