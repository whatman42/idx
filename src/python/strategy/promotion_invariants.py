"""PROMOTED invariants + fill matrix + EvidencePackage candidacy wiring.

Imported by promotion_gate and tests. No circular imports of gate evaluation.
"""
from __future__ import annotations

from typing import Any

from src.python.strategy.contracts import StrategyLifecycle


PROMOTED_REQUIRED_FIELDS = (
    "promotion_id",
    "authority_id",
    "evidence_id",
    "strategy_version",
    "dataset_hash",
    "feature_hash",
    "cost_model",
    "baseline_id",
)


def promoted_record_missing_fields(decision: Any) -> list[str]:
    missing: list[str] = []
    for name in PROMOTED_REQUIRED_FIELDS:
        val = getattr(decision, name, None)
        if val is None or (isinstance(val, str) and not str(val).strip()):
            missing.append(name)
    status = getattr(decision, "lifecycle_status", None)
    if status != StrategyLifecycle.PROMOTED.value:
        missing.append("lifecycle_status")
    if not getattr(decision, "approved", False):
        missing.append("approved")
    return missing


def assert_promoted_invariants(decision: Any) -> None:
    missing = promoted_record_missing_fields(decision)
    if missing:
        raise RuntimeError(f"promoted_invariant_fail missing={missing}")


def fill_allowed_for_status(status: str) -> bool:
    return str(status or "").upper() == StrategyLifecycle.PROMOTED.value


def assert_fill_allowed_for_status(status: str) -> None:
    if not fill_allowed_for_status(status):
        raise RuntimeError(f"fill_blocked status={status}")
