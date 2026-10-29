"""agent-chaos: chaos engineering for AI agents."""
from . import faults, oracles, policies
from .baseline import ScoreDiff, compare_baseline, save_baseline
from .core import (
    ChaosError,
    Event,
    Kind,
    Level,
    RunContext,
    StepLimitExceeded,
    ToolError,
    ToolTimeout,
    Verdict,
)
from .core.errors import ReplayedError, ReplayMismatch
from .record import ReplayFault, load_replay, save_trace
from .runner import RunSummary, Scenario, ScenarioResult, TrialResult, run_all, run_scenario, run_trial
from .shrink import shrink

__version__ = "0.2.0"

__all__ = [
    "faults", "oracles", "policies", "ChaosError", "Event", "Kind", "Level", "RunContext",
    "StepLimitExceeded", "ToolError", "ToolTimeout", "Verdict", "RunSummary", "Scenario",
    "ScenarioResult", "TrialResult", "run_all", "run_scenario", "run_trial",
    "ReplayFault", "load_replay", "save_trace", "ReplayMismatch", "ReplayedError", "shrink",
    "ScoreDiff", "compare_baseline", "save_baseline",
    "__version__",
]
