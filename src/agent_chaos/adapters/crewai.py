"""CrewAI adapter: wrap CrewAI tools so they run through the fault engine.

CrewAI custom tools subclass ``crewai.tools.BaseTool`` and override ``_run``/``_arun`` directly
(no ``func``/``coroutine`` attributes the way LangChain's decorator-built tools have), which
``adapters/tools.py``'s ``wrap_tool`` already covers as a fallback. This module just re-exports it
under a CrewAI-specific name for discoverability; there is no CrewAI-specific logic to add. No
hard dependency on ``crewai``.

    from agent_chaos.adapters.crewai import wrap_tools

    wrap_tools(ctx, [search_tool, refund_tool], side_effect=lambda t: t.name == "refund_tool")
    crew = Crew(agents=[...], tasks=[...])
"""
from __future__ import annotations

from .tools import wrap_tool, wrap_tools  # noqa: F401 - the adapter, re-exported
