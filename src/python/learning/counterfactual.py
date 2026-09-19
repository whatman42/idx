"""Counterfactual Engine — what if a different decision was taken?"""
from __future__ import annotations

from src.python.learning.contracts import (
    CounterfactualReport,
    CounterfactualScenario,
    SignalEpisode,
)


def analyze_counterfactuals(ep: SignalEpisode) -> CounterfactualReport:
    """Simple deterministic counterfactuals from episode fields."""
    actual = float(ep.r_multiple or 0.0)
    scenarios: list[CounterfactualScenario] = []

    scenarios.append(CounterfactualScenario(
        name="HOLD",
        description="No trade",
        hypothetical_r=0.0,
        delta_r=0.0 - actual,
        category="signal",
    ))

    alt_r = -0.5 * actual if abs(actual) > 1e-9 else 0.0
    scenarios.append(CounterfactualScenario(
        name="ALT_STRATEGY",
        description="Opposite ensemble member dominant",
        hypothetical_r=alt_r,
        delta_r=alt_r - actual,
        category="strategy",
    ))

    late_r = actual * 0.3
    scenarios.append(CounterfactualScenario(
        name="ENTRY_PLUS_1",
        description="Enter one bar later",
        hypothetical_r=late_r,
        delta_r=late_r - actual,
        category="timing",
    ))

    if actual < 0:
        tight = max(actual, -0.7)
    else:
        tight = actual * 0.9
    scenarios.append(CounterfactualScenario(
        name="TIGHTER_SL",
        description="SL closer to entry",
        hypothetical_r=tight,
        delta_r=tight - actual,
        category="risk",
    ))

    scenarios.append(CounterfactualScenario(
        name="REGIME_BLOCK",
        description="No trade due to regime filter",
        hypothetical_r=0.0,
        delta_r=0.0 - actual,
        category="signal",
    ))

    if actual < 0:
        best = max(scenarios, key=lambda s: s.hypothetical_r)
        dominant = best.category
    else:
        dominant = "market"

    return CounterfactualReport(
        episode_id=ep.episode_id,
        actual_r=actual,
        scenarios=scenarios,
        dominant_category=dominant,
    )
