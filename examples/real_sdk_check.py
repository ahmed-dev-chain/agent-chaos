"""Manual verification: confirm agent-chaos actually intercepts real OpenAI/Anthropic SDK calls.

Not part of the automated test suite — it needs live API keys and makes real network calls, which
would contradict the project's "no API key needed, works offline" promise for its own CI. Run it
by hand after installing the extra and filling in ``.env`` (copy from ``.env.example``):

    pip install -e ".[real-sdk]"
    python examples/real_sdk_check.py

For each provider with a key set, this makes one real call with no fault (should succeed
normally) and one real call with a Timeout fault on that provider's endpoint (should raise
``agent_chaos.ToolTimeout`` before the real request is ever sent) — proving the SDK's outbound
httpx traffic genuinely passes through the fault engine, not just through a mock.
"""
from __future__ import annotations

import asyncio
import os

from agent_chaos import RunContext, ToolTimeout, faults
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


async def main() -> None:
    openai_key = os.environ.get("OPENAI_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
    if not openai_key and not anthropic_key:
        print("No OPENAI_API_KEY or ANTHROPIC_API_KEY set (see .env.example). Nothing to check.")
        return
    if openai_key:
        print("OpenAI:")
        await _check_openai(openai_key)
    if anthropic_key:
        print("Anthropic:")
        await _check_anthropic(anthropic_key)


if __name__ == "__main__":
    asyncio.run(main())
