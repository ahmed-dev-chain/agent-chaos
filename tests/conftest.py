import importlib.metadata as md

# When the package is installed, pytest loads the plugin through its entry point.
# Otherwise (running from a source checkout) register it explicitly.
_installed = any(ep.name == "agent_chaos" for ep in md.entry_points(group="pytest11"))
pytest_plugins = [] if _installed else ["agent_chaos.pytest_plugin"]
