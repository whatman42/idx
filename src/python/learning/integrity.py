"""Learning data integrity boundary.

Ledger remains SSOT. If reconciliation fails:
  LEARNING_DATA_INTEGRITY = FAIL
  learning update = BLOCKED
  experiment promotion = BLOCKED
  research candidacy = BLOCKED

Never modify the ledger to make reconciliation pass.
Never silently repair episode values.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from src.python.learning.attribution import attribute_episode
from src.python.learning.contracts import (
    AttributionReport,
    IntegrityResult,
    SignalEpisode,
)

PNL_TOLERANCE = 1.0
PRICE_TOLERANCE = 1e-6
QTY_TOLERANCE = 1e-9


@dataclass
class LedgerTradeFact:
    """Minimal ledger closed-trade facts for field-level reconcile."""
    signal_id: str = ""
    episode_id: str = ""
    symbol: str = ""
    entry_price: Optional[float] = None
    exit_price: Optional[float] = None
    quantity: Optional[float] = None
    entry_timestamp: Optional[str] = None
    exit_timestamp: Optional[str] = None
    fees: Optional[float] = None
    slippage: Optional[float] = None
    realized_pnl: Optional[float] = None
    trade_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "episode_id": self.episode_id,
            "symbol": self.symbol,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "quantity": self.quantity,
            "entry_timestamp": self.entry_timestamp,
            "exit_timestamp": self.exit_timestamp,
            "fees": self.fees,
            "slippage": self.slippage,
            "realized_pnl": self.realized_pnl,
            "trade_id": self.trade_id,
        }


def _fneq(a: Optional[float], b: Optional[float], tol: float) -> bool:
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    return abs(float(a) - float(b)) > tol


def reconcile_episode_fields(
    episodes: Sequence[SignalEpisode],
    ledger_facts: Sequence[LedgerTradeFact],
    *,
    price_tol: float = PRICE_TOLERANCE,
    qty_tol: float = QTY_TOLERANCE,
    pnl_tol: float = PNL_TOLERANCE,
) -> IntegrityResult:
    """Field-level Ledger ↔ Episode reconciliation. Ledger is SSOT."""
    issues: list[str] = []
    by_ep = {e.episode_id: e for e in episodes if e.episode_id}
    by_sig = {e.signal_id: e for e in episodes if e.signal_id}
    by_fill = {e.fill_id: e for e in episodes if e.fill_id}
    seen_ledger_ids: set[str] = set()

    for fact in ledger_facts:
        key = fact.trade_id or fact.episode_id or fact.signal_id
        if key and key in seen_ledger_ids:
            issues.append(f"duplicate_ledger_event:{key}")
        if key:
            seen_ledger_ids.add(key)

        ep: Optional[SignalEpisode] = None
        if fact.episode_id and fact.episode_id in by_ep:
            ep = by_ep[fact.episode_id]
        elif fact.signal_id and fact.signal_id in by_sig:
            ep = by_sig[fact.signal_id]
        elif fact.trade_id and fact.trade_id in by_fill:
            ep = by_fill[fact.trade_id]

        if ep is None:
            issues.append(f"orphan_ledger:{key or fact.symbol}")
            continue

        if fact.symbol and ep.symbol and fact.symbol != ep.symbol:
            issues.append(f"symbol_mismatch:{ep.episode_id}")
        if fact.signal_id and ep.signal_id and fact.signal_id != ep.signal_id:
            issues.append(f"signal_identity_mismatch:{ep.episode_id}")
        if _fneq(fact.entry_price, ep.entry_px if ep.entry_px else None, price_tol):
            if fact.entry_price is not None and ep.entry_px:
                issues.append(f"entry_mismatch:{ep.episode_id}")
        if _fneq(fact.exit_price, ep.exit_px if ep.exit_px else None, price_tol):
            if fact.exit_price is not None and ep.exit_px:
                issues.append(f"exit_mismatch:{ep.episode_id}")
        if _fneq(fact.quantity, ep.qty if ep.qty else None, qty_tol):
            if fact.quantity is not None and ep.qty:
                issues.append(f"quantity_mismatch:{ep.episode_id}")
        if _fneq(fact.fees, ep.fees if ep.fees else None, pnl_tol):
            if fact.fees is not None:
                issues.append(f"fee_mismatch:{ep.episode_id}")
        if _fneq(fact.realized_pnl, ep.pnl if ep.pnl else None, pnl_tol):
            if fact.realized_pnl is not None:
                issues.append(f"pnl_mismatch:{ep.episode_id}")
        if fact.entry_timestamp and ep.meta.get("entry_timestamp"):
            if str(fact.entry_timestamp) != str(ep.meta.get("entry_timestamp")):
                issues.append(f"timestamp_mismatch:{ep.episode_id}")

    ledger_ep_ids = {f.episode_id for f in ledger_facts if f.episode_id}
    ledger_sig_ids = {f.signal_id for f in ledger_facts if f.signal_id}
    for e in episodes:
        if e.lifecycle not in ("COMPLETED", "ATTRIBUTED"):
            continue
        if e.outcome in ("OPEN", "SKIPPED"):
            continue
        matched = (e.episode_id in ledger_ep_ids) or (e.signal_id and e.signal_id in ledger_sig_ids)
        if ledger_facts and not matched:
            issues.append(f"orphan_episode:{e.episode_id}")

    base = reconcile_episode_pnl(episodes, ledger_realized_pnl=None)
    for i in base.issues:
        if i not in issues and not i.startswith("no_external"):
            issues.append(i)

    ledger_pnl = float(sum(float(f.realized_pnl or 0) for f in ledger_facts)) if ledger_facts else base.ledger_pnl
    hard = [i for i in issues if not i.startswith("no_external")]
    ok = len(hard) == 0
    return IntegrityResult(
        ok=ok,
        ledger_pnl=ledger_pnl,
        episode_pnl=base.episode_pnl,
        attribution_pnl=base.attribution_pnl,
        delta_ledger_episode=abs(ledger_pnl - base.episode_pnl) if ledger_facts else base.delta_ledger_episode,
        delta_episode_attribution=base.delta_episode_attribution,
        issues=issues,
        learning_data_integrity="PASS" if ok else "FAIL",
        blocked=not ok,
    )


def reconcile_episode_pnl(
    episodes: Sequence[SignalEpisode],
    *,
    ledger_realized_pnl: Optional[float] = None,
    closed_trade_pnls: Optional[Sequence[float]] = None,
    attributions: Optional[Sequence[AttributionReport]] = None,
    tolerance: float = PNL_TOLERANCE,
) -> IntegrityResult:
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

    for e in completed:
        if not e.fill_id:
            issues.append(f"completed_without_fill_id:{e.episode_id}")
        if e.lifecycle == "COMPLETED" and e.outcome == "OPEN":
            issues.append(f"completed_but_outcome_open:{e.episode_id}")
        if e.lifecycle == "OPEN" and e.exit_px > 0 and e.pnl != 0:
            issues.append(f"open_with_exit_pnl:{e.episode_id}")

    if attributions is not None:
        ep_ids = {e.episode_id for e in episodes}
        for a in attributions:
            aid = getattr(a, "episode_id", None) or getattr(a, "signal_id", None)
            if aid and aid not in ep_ids and aid not in {e.signal_id for e in episodes}:
                issues.append(f"orphan_attribution:{aid}")

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
    if result.learning_data_integrity == "FAIL" or result.blocked:
        return {
            "learning_update": "BLOCKED",
            "experiment_promotion": "BLOCKED",
            "knowledge_validation": "BLOCKED",
            "research": "BLOCKED",
            "evidence": "INVALID",
            "promotion_candidacy": "BLOCKED",
            "reason": "LEARNING_DATA_INTEGRITY_FAIL",
            "issues": list(result.issues),
        }
    return {
        "learning_update": "ALLOW",
        "experiment_promotion": "ALLOW_CANDIDATE_ONLY",
        "knowledge_validation": "ALLOW",
        "research": "ALLOW",
        "evidence": "ALLOW",
        "promotion_candidacy": "ALLOW_CANDIDATE_ONLY",
        "reason": "PASS",
        "issues": [],
    }
