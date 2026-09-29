"""Crypto PromotionGate — independent of IDX PromotionGate.

Evidence → gate → lifecycle status only.
Never enables LIVE_EXECUTION. Never submits orders. Never writes IDX ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CryptoPromotionDecision:
    approved: bool
    strategy_id: str
    strategy_version: str
    lifecycle_status: str  # RESEARCH | EVALUATED | CANDIDATE | REJECTED
    reasons: list[str] = field(default_factory=list)
    live_execution: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "lifecycle_status": self.lifecycle_status,
            "reasons": list(self.reasons),
            "live_execution": False,
            "domain": "CRYPTO",
        }


class CryptoPromotionGate:
    """Fail-closed independent gate. Paper ops may run RESEARCH strategies explicitly."""

    def evaluate(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        evidence: Optional[dict[str, Any]] = None,
        min_trades: int = 30,
        min_expectancy: float = 0.0,
    ) -> CryptoPromotionDecision:
        reasons: list[str] = []
        ev = evidence or {}
        if not strategy_id.startswith("crypto_"):
            reasons.append("STRATEGY_ID_NOT_CRYPTO_NAMESPACE")
            return CryptoPromotionDecision(
                False, strategy_id, strategy_version, "REJECTED", reasons
            )
        n = int(ev.get("n_trades") or ev.get("signals_count") or 0)
        if n < min_trades:
            reasons.append(f"INSUFFICIENT_TRADES:{n}<{min_trades}")
        exp = float(ev.get("expectancy") or 0.0)
        if exp < min_expectancy and n > 0:
            reasons.append("NEGATIVE_EXPECTANCY")
        if reasons:
            return CryptoPromotionDecision(
                False, strategy_id, strategy_version, "RESEARCH", reasons
            )
        return CryptoPromotionDecision(
            True,
            strategy_id,
            strategy_version,
            "CANDIDATE",
            ["EVIDENCE_THRESHOLD_MET"],
        )
