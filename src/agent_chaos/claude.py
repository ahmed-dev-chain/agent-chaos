"""Call Claude with either an API key or a Claude Pro/Max/Team subscription -- no code change
between the two, and the subscription path needs no extra dependency at all.

With ``ANTHROPIC_API_KEY`` set, calls go through the Anthropic SDK (needs ``pip install
anthropic``, e.g. via the ``real-sdk`` extra). Without it, calls shell out to the local ``claude``
CLI (Claude Code) in non-interactive mode, authenticated by whatever ``claude login`` already set
up -- the same way most Claude Code-based tools on GitHub work: clone, and it runs with your
existing subscription, no separate billed key required.

Either way this is a plain synchronous function, so it's just another callable to hand to
``ctx.wrap``/``ctx.awrap`` -- fault injection happens at that boundary, not inside this module, so
every fault in the catalog works against it the same as any other tool::

    from agent_chaos.claude import call_claude

    ask = ctx.wrap("claude", call_claude, kind=Kind.MODEL_CALL)
    reply = ask("Summarize this ticket: ...")
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

DEFAULT_MODEL = "claude-sonnet-4-5"


class ClaudeUnavailable(RuntimeError):
    """Neither ANTHROPIC_API_KEY nor a logged-in ``claude`` CLI is available."""


def call_claude(
    prompt: str,
    *,
    model: str = DEFAULT_MODEL,
    system: str | None = None,
    timeout: float = 120.0,
    prefer: str = "auto",
) -> str:
    """Return Claude's text reply to ``prompt``.

    ``prefer`` picks the backend: ``"auto"`` (default) uses the API if ``ANTHROPIC_API_KEY`` is
    set, otherwise the CLI; ``"api"``/``"cli"`` force one or the other regardless of the
    environment. Raises :class:`ClaudeUnavailable` if the chosen backend isn't usable (no key for
    ``"api"``; no ``claude`` on PATH, or it exits non-zero -- e.g. not logged in -- for ``"cli"``).
    """
    if prefer not in ("auto", "api", "cli"):
        raise ValueError(f"prefer must be 'auto', 'api' or 'cli', got {prefer!r}")
    use_api = prefer == "api" or (prefer == "auto" and bool(os.environ.get("ANTHROPIC_API_KEY")))
    if use_api:
        return _call_api(prompt, model=model, system=system)
    return _call_cli(prompt, model=model, system=system, timeout=timeout)


def _call_api(prompt: str, *, model: str, system: str | None) -> str:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ClaudeUnavailable("prefer='api' but ANTHROPIC_API_KEY is not set")
    try:
        import anthropic  # optional dependency
    except ImportError as exc:
        raise ClaudeUnavailable("prefer='api' needs the anthropic package: pip install anthropic") from exc

    client = anthropic.Anthropic()
    kwargs: dict = {"model": model, "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    message = client.messages.create(**kwargs)
    return "".join(block.text for block in message.content if block.type == "text")


def _call_cli(prompt: str, *, model: str, system: str | None, timeout: float) -> str:
    claude_bin = shutil.which("claude")
    if not claude_bin:
        raise ClaudeUnavailable(
            "prefer='cli' (or no ANTHROPIC_API_KEY set) but the `claude` CLI isn't on PATH. "
            "Install Claude Code and run `claude login`, or set ANTHROPIC_API_KEY instead."
        )
    cmd = [claude_bin, "-p", prompt, "--output-format", "json", "--model", model]
    if system:
        cmd += ["--append-system-prompt", system]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise ClaudeUnavailable(f"claude CLI timed out after {timeout:.0f}s") from exc
    if proc.returncode != 0:
        raise ClaudeUnavailable(
            f"claude CLI exited {proc.returncode}: {(proc.stderr or proc.stdout).strip()} "
            "-- make sure you're logged in: `claude login`"
        )
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeUnavailable(f"claude CLI produced non-JSON output: {proc.stdout[:200]!r}") from exc
    if data.get("is_error"):
        raise ClaudeUnavailable(f"claude CLI reported an error: {data.get('result')!r}")
    return data.get("result", "")
