"""Production control plane — Promotion status binds ops path.

Statuses:
  RESEARCH  → blocked from production fills; may appear in SHADOW report
  SHADOW    → scored in ops for comparison only; never fills
  PROMOTED  → eligible for production signal → risk gate → paper fill
  REJECTED / EXPIRED / RETIRED → blocked

SMA20 (rule_sma20) remains the only PROMOTED baseline until EvidencePackage
clears PromotionGate for a challenger.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from src.python.strategy.registry import STRATEGY_REGISTRY, get_strategy, list_strategies, promoted_ids

PRODUCTION_ELIGIBLE = frozenset({"PROMOTED"})
SHADOW_ELIGIBLE = frozenset({"RESEARCH", "SHADOW", "CANDIDATE"})
BLOCKED = frozenset({"REJECTED", "EXPIRED", "RETIRED"})


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
    status = str(spec.status or "RESEARCH").upper()
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
        "enforcement": "ops_path_requires_PROMOTED",
        "version": "production_control_v1",
    }
