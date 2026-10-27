"""Resilience score with a Wilson confidence interval."""
from __future__ import annotations

import math

Z95 = 1.959963984540054


def wilson_interval(successes: float, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a proportion. Behaves well for small n."""
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def pass_rate(survived: int, degraded: int, n: int) -> float:
    return (survived + 0.5 * degraded) / n if n else 0.0
