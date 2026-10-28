"""Manual verification: confirm agent-chaos actually intercepts real OpenAI/Anthropic/Claude calls.

Not part of the automated test suite — it needs live credentials (an API key, or just a logged-in
Claude Code subscription) and makes real calls, which would contradict the project's "no API key
needed, works offline" promise for its own CI. Run it by hand after installing the extra and
filling in ``.env`` (copy from ``.env.example`` — entirely optional for the Claude-CLI check):

    pip install -e ".[real-sdk]"
    python examples/real_sdk_check.py

For each provider with a key set, `_check_openai`/`_check_anthropic` make one real call with no
fault (should succeed normally) and one real call with a Timeout fault on that provider's endpoint
(should raise ``agent_chaos.ToolTimeout`` before the real request is ever sent) — proving the SDK's
outbound httpx traffic genuinely passes through the fault engine, not just through a mock.

`_check_claude_universal` instead calls `agent_chaos.claude.call_claude`, which works with an
ANTHROPIC_API_KEY *or*, with none set, falls back to the local `claude` CLI authenticated via
`claude login` — a Claude Pro/Max/Team subscription, no billed API key required. It proves the
same thing a different way: fault injection happens at the `ctx.wrap` boundary, not inside
`call_claude`, so it works identically regardless of which backend is actually calling Claude.
"""
from __future__ import annotations

import asyncio
import os
import shutil

from agent_chaos import Kind, RunContext, ToolTimeout, faults
from agent_chaos.claude import call_claude
from agent_chaos.intercept import patch_httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


async def _check_openai(api_key: str) -> None:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    kwargs = {"model": "gpt-4o-mini", "max_tokens": 5, "messages": [{"role": "user", "content": "say ok"}]}

    ctx = RunContext(0, [])
    with patch_httpx(ctx):
        await client.chat.completions.create(**kwargs)
    print("  passthrough call succeeded")

    ctx = RunContext(0, [faults.Timeout("http=api.openai.com")])
    try:
        with patch_httpx(ctx):
            await client.chat.completions.create(**kwargs)
    except ToolTimeout:
        print("  injected timeout correctly intercepted the real SDK call")
    else:
        raise AssertionError("expected ToolTimeout: the httpx patch did not intercept the OpenAI SDK")


async def _check_anthropic(api_key: str) -> None:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    kwargs = {"model": "claude-3-5-haiku-latest", "max_tokens": 5,
              "messages": [{"role": "user", "content": "say ok"}]}

    ctx = RunContext(0, [])
    with patch_httpx(ctx):
        await client.messages.create(**kwargs)
    print("  passthrough call succeeded")

    ctx = RunContext(0, [faults.Timeout("http=api.anthropic.com")])
    try:
        with patch_httpx(ctx):
            await client.messages.create(**kwargs)
    except ToolTimeout:
        print("  injected timeout correctly intercepted the real SDK call")
    else:
        raise AssertionError("expected ToolTimeout: the httpx patch did not intercept the Anthropic SDK")


def _check_claude_universal() -> None:
    ctx = RunContext(0, [])
    ask = ctx.wrap("claude", call_claude, kind=Kind.MODEL_CALL)
    reply = ask("Reply with exactly one word: OK")
    print(f"  passthrough call succeeded: {reply[:60]!r}")

    ctx = RunContext(0, [faults.Timeout("model=claude")])
    ask = ctx.wrap("claude", call_claude, kind=Kind.MODEL_CALL)
    try:
        ask("Reply with exactly one word: OK")
    except ToolTimeout:
        print("  injected timeout correctly intercepted the call")
    else:
        raise AssertionError("expected ToolTimeout: fault injection did not intercept call_claude")


async def main() -> None:
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    claude_cli = shutil.which("claude")

    if not openai_key and not anthropic_key and not claude_cli:
        print("No OPENAI_API_KEY/ANTHROPIC_API_KEY set and no `claude` CLI on PATH. Nothing to check.")
        return
    if openai_key:
        print("OpenAI:")
        await _check_openai(openai_key)
    if anthropic_key:
        print("Anthropic:")
        await _check_anthropic(anthropic_key)
    if anthropic_key or claude_cli:
        print(f"Claude ({'API key' if anthropic_key else 'claude CLI / subscription'}):")
        _check_claude_universal()


if __name__ == "__main__":
    asyncio.run(main())
