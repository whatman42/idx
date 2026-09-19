"""Production control plane — only PROMOTED may fill.

Statuses (StrategyLifecycle):
  RESEARCH   → shadow/report only
  EVALUATED  → evidence collected; no fill
  CANDIDATE  → evidence gate passed; awaiting authority; no fill
  PROMOTED   → production path allowed
  REJECTED   → blocked
  RETIRED    → blocked

Performance does not execute. Authority + status does.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.python.strategy.contracts import StrategyLifecycle
from src.python.strategy.registry import STRATEGY_REGISTRY, get_strategy, list_strategies, promoted_ids

PRODUCTION_ELIGIBLE = frozenset({StrategyLifecycle.PROMOTED.value, "PROMOTED"})
SHADOW_ELIGIBLE = frozenset({
    StrategyLifecycle.RESEARCH.value,
    StrategyLifecycle.EVALUATED.value,
    StrategyLifecycle.CANDIDATE.value,
    "RESEARCH", "EVALUATED", "CANDIDATE", "SHADOW",
})
BLOCKED = frozenset({
    StrategyLifecycle.REJECTED.value,
    StrategyLifecycle.RETIRED.value,
    "REJECTED", "RETIRED", "EXPIRED",
})


@dataclass
class StrategyEligibility:
    strategy_id: str
    status: str
    production_allowed: bool
    shadow_allowed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def eligibility(strategy_id: str) -> StrategyEligibility:
    try:
        spec = get_strategy(strategy_id)
    except KeyError:
        return StrategyEligibility(
            strategy_id=strategy_id,
            status="UNKNOWN",
            production_allowed=False,
            shadow_allowed=False,
            reason="unknown_strategy",
        )
    status = str(spec.status or StrategyLifecycle.RESEARCH.value).upper()
    if status in BLOCKED:
        return StrategyEligibility(strategy_id, status, False, False, f"blocked:{status}")
    prod = status in PRODUCTION_ELIGIBLE
    shadow = status in SHADOW_ELIGIBLE or prod
    if prod:
        reason = "PROMOTED"
    elif status in SHADOW_ELIGIBLE:
        reason = f"shadow_only:{status}"
    else:
        reason = f"not_eligible:{status}"
    return StrategyEligibility(strategy_id, status, prod, shadow, reason)


def assert_production_allowed(strategy_id: str) -> None:
    """Runtime enforcement — never score>threshold based."""
    e = eligibility(strategy_id)
    if not e.production_allowed:
        raise RuntimeError(
            f"production_blocked strategy={strategy_id} status={e.status} reason={e.reason}"
        )


def production_strategy_ids() -> list[str]:
    return list(promoted_ids())


def shadow_strategy_ids() -> list[str]:
    out = []
    for s in list_strategies():
        e = eligibility(s.strategy_id)
        if e.shadow_allowed and not e.production_allowed:
            out.append(s.strategy_id)
    return out


def control_plane_summary() -> dict[str, Any]:
    return {
        "production": production_strategy_ids(),
        "shadow": shadow_strategy_ids(),
        "registry_count": len(STRATEGY_REGISTRY),
        "enforcement": "ops_path_requires_PROMOTED_status_only",
        "lifecycle": [s.value for s in StrategyLifecycle],
        "version": "production_control_v2",
    }
