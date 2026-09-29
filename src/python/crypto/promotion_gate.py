"""Crypto PromotionGate — independent of IDX PromotionGate.

Evidence → gate → strategy lifecycle status only.
Never enables LIVE_EXECUTION. Never submits orders.
Shadow (*_shadow) max lifecycle via this path: CANDIDATE (research review).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.python.crypto.strategy_status import StrategyStatusRecord, set_status


@dataclass
class CryptoPromotionDecision:
    approved: bool
    strategy_id: str
    strategy_version: str
    lifecycle_status: str
    reasons: list[str] = field(default_factory=list)
    live_execution: bool = False
    evidence_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "lifecycle_status": self.lifecycle_status,
            "reasons": list(self.reasons),
            "live_execution": False,
            "domain": "CRYPTO",
            "evidence_hash": self.evidence_hash,
        }


def _is_shadow(strategy_id: str) -> bool:
    return strategy_id.endswith("_shadow") or strategy_id == "crypto_momentum_shadow"


class CryptoPromotionGate:
    def evaluate(
        self,
        *,
        strategy_id: str,
        strategy_version: str,
        evidence: Optional[dict[str, Any]] = None,
        min_trades: int = 30,
        min_expectancy: float = 0.0,
        max_drawdown: float = 0.40,
        promote_to_paper_allowed: bool = False,
        persist: bool = True,
        status_path: Optional[str] = None,
    ) -> CryptoPromotionDecision:
        reasons: list[str] = []
        ev = evidence or {}
        if not strategy_id.startswith("crypto_"):
            reasons.append("STRATEGY_ID_NOT_CRYPTO_NAMESPACE")
            return self._finish(
                False, strategy_id, strategy_version, "REJECTED", reasons, "", persist, status_path
            )

        hard = list(ev.get("hard_reject") or [])
        n = int(ev.get("n_trades") or ev.get("signals_count") or 0)
        exp = float(ev.get("expectancy") or 0.0)
        mdd = float(ev.get("max_drawdown") or 0.0)
        eh = str(ev.get("package_hash") or "")

        if hard:
            reasons.extend([f"HARD:{c}" for c in hard])
        if n < min_trades:
            reasons.append(f"INSUFFICIENT_TRADES:{n}<{min_trades}")
        if exp < min_expectancy and n > 0:
            reasons.append("NEGATIVE_EXPECTANCY")
        if mdd > max_drawdown and n > 0:
            reasons.append(f"MAX_DRAWDOWN:{mdd:.3f}")

        if reasons:
            status = "REJECTED" if any(r.startswith("HARD:") for r in reasons) else "RESEARCH"
            if any(r.startswith("INSUFFICIENT") for r in reasons) and not any(
                r.startswith("HARD:") for r in reasons
            ):
                status = "RESEARCH"
            return self._finish(
                False, strategy_id, strategy_version, status, reasons, eh, persist, status_path
            )

        if _is_shadow(strategy_id):
            if promote_to_paper_allowed:
                reasons = [
                    "EVIDENCE_THRESHOLD_MET",
                    "SHADOW_CANNOT_AUTO_PAPER",
                    "SHADOW_RESEARCH_ONLY",
                ]
            else:
                reasons = ["EVIDENCE_THRESHOLD_MET", "SHADOW_RESEARCH_ONLY"]
            return self._finish(
                True, strategy_id, strategy_version, "CANDIDATE", reasons, eh, persist, status_path
            )

        status = "PAPER_ALLOWED" if promote_to_paper_allowed else "CANDIDATE"
        reasons = ["EVIDENCE_THRESHOLD_MET"]
        if status == "PAPER_ALLOWED":
            reasons.append("EXPLICIT_PAPER_ALLOWED")
        return self._finish(
            True, strategy_id, strategy_version, status, reasons, eh, persist, status_path
        )

    def _finish(
        self,
        approved: bool,
        strategy_id: str,
        strategy_version: str,
        status: str,
        reasons: list[str],
        eh: str,
        persist: bool,
        status_path: Optional[str],
    ) -> CryptoPromotionDecision:
        dec = CryptoPromotionDecision(
            approved, strategy_id, strategy_version, status, reasons, evidence_hash=eh
        )
        if persist:
            set_status(
                StrategyStatusRecord(strategy_id, strategy_version, status, reasons, eh),
                path=status_path,
            )
        return dec
