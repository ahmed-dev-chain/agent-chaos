"""Exceptions raised by injected faults and by the engine."""
from __future__ import annotations


class ChaosError(Exception):
    """Base class for all agent-chaos exceptions."""


class ToolError(ChaosError):
    """A tool or API answered with an error status (injected)."""

    def __init__(self, status: int = 500, message: str = "injected error"):
        super().__init__(f"{status}: {message}")
        self.status = status


class ToolTimeout(ChaosError):
    """A tool never answered in time (injected)."""


class StepLimitExceeded(ChaosError):
    """The target made more calls than the hard step cap allows (likely a loop)."""
