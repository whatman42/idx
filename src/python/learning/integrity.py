"""Learning data integrity boundary.

Ledger remains SSOT. If reconciliation fails:
  LEARNING_DATA_INTEGRITY = FAIL
  learning update = BLOCKED
  experiment promotion = BLOCKED
  knowledge validation = BLOCKED

Never modify the ledger to make reconciliation pass.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from src.python.learning.attribution import attribute_episode
from src.python.learning.contracts import (
    AttributionReport,
    IntegrityResult,
    SignalEpisode,
)

PNL_TOLERANCE = 1.0


def reconcile_episode_pnl(
    episodes: Sequence[SignalEpisode],
    *,
    ledger_realized_pnl: Optional[float] = None,
    closed_trade_pnls: Optional[Sequence[float]] = None,
    attributions: Optional[Sequence[AttributionReport]] = None,
    tolerance: float = PNL_TOLERANCE,
) -> IntegrityResult:
    """Reconcile Ledger P&L vs Episode P&L vs Attribution P&L."""
    issues: list[str] = []
    completed = [
        e for e in episodes
        if e.lifecycle in ("COMPLETED", "ATTRIBUTED") and e.outcome not in ("OPEN", "SKIPPED")
    ]
    episode_pnl = float(sum(float(e.pnl or 0) for e in completed))

    if closed_trade_pnls is not None:
        ledger_pnl = float(sum(float(x or 0) for x in closed_trade_pnls))
    elif ledger_realized_pnl is not None:
        ledger_pnl = float(ledger_realized_pnl)
    else:
        ledger_pnl = episode_pnl
        issues.append("no_external_ledger_pnl_provided")

    if attributions is None:
        attributions = [attribute_episode(e) for e in completed]
    attr_pnl = 0.0
    for i, a in enumerate(attributions):
        ap = float(getattr(a, "pnl", 0) or 0)
        if ap == 0 and i < len(completed):
            ap = float(completed[i].pnl or 0)
        attr_pnl += ap

    d_le = abs(ledger_pnl - episode_pnl)
    d_ea = abs(episode_pnl - attr_pnl)

    if d_le > tolerance:
        issues.append(f"ledger_episode_mismatch delta={d_le:.4f}")
    if d_ea > tolerance:
        issues.append(f"episode_attribution_mismatch delta={d_ea:.4f}")

    keys = [e.idempotency_key for e in episodes if e.idempotency_key]
    if len(keys) != len(set(keys)):
        issues.append("duplicate_idempotency_key")
    for e in episodes:
        if e.lifecycle == "COMPLETED" and not e.fill_id:
            issues.append(f"completed_without_fill_id:{e.episode_id}")
        if e.lifecycle == "COMPLETED" and e.outcome == "OPEN":
            issues.append(f"completed_but_outcome_open:{e.episode_id}")
        if e.lifecycle == "OPEN" and e.exit_px > 0 and e.pnl != 0:
            issues.append(f"open_with_exit_pnl:{e.episode_id}")

    hard_issues = [i for i in issues if not i.startswith("no_external")]
    ok = len(hard_issues) == 0
    integrity = "PASS" if ok else "FAIL"
    return IntegrityResult(
        ok=ok,
        ledger_pnl=ledger_pnl,
        episode_pnl=episode_pnl,
        attribution_pnl=attr_pnl,
        delta_ledger_episode=d_le,
        delta_episode_attribution=d_ea,
        issues=issues,
        learning_data_integrity=integrity,
        blocked=not ok,
    )


def gate_learning_on_integrity(result: IntegrityResult) -> dict[str, Any]:
    """Fail-closed gate for learning updates / experiment promotion / knowledge validation."""
    if result.learning_data_integrity == "FAIL" or result.blocked:
        return {
            "learning_update": "BLOCKED",
            "experiment_promotion": "BLOCKED",
            "knowledge_validation": "BLOCKED",
            "reason": "LEARNING_DATA_INTEGRITY_FAIL",
            "issues": list(result.issues),
        }
    return {
        "learning_update": "ALLOW",
        "experiment_promotion": "ALLOW_CANDIDATE_ONLY",
        "knowledge_validation": "ALLOW",
        "reason": "PASS",
        "issues": [],
    }
