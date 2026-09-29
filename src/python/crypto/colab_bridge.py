"""Crypto Colab research bridge — compute only.

OHLCV → training/WFA → candidate → EvidencePackage → CryptoPromotionGate

HARD:
  cannot set LIVE_EXECUTION
  cannot submit exchange orders
  cannot write CryptoPaperLedger
  cannot auto-promote to paper without CryptoPromotionGate
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class CryptoColabJobResult:
    ok: bool
    job_id: str
    strategy_id: str = ""
    strategy_version: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    live_execution: bool = False
    orders_submitted: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "job_id": self.job_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "evidence": self.evidence,
            "notes": list(self.notes),
            "live_execution": False,
            "orders_submitted": 0,
            "domain": "CRYPTO",
            "authority": "RESEARCH_ONLY",
        }


def run_crypto_colab_research_stub(
    *,
    job_id: str,
    strategy_id: str = "crypto_rule_sma20",
    strategy_version: str = "crypto_sma_v0",
    bars_meta: Optional[dict[str, Any]] = None,
) -> CryptoColabJobResult:
    """Placeholder research job — no GPU, no order path."""
    notes = [
        "COLAB_RESEARCH_STUB",
        "no_live_execution",
        "no_order_submission",
        "requires_CryptoPromotionGate_for_any_status_change",
    ]
    if bars_meta:
        notes.append(f"bars_meta_keys={list(bars_meta.keys())}")
    return CryptoColabJobResult(
        ok=True,
        job_id=job_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        evidence={
            "n_trades": 0,
            "expectancy": 0.0,
            "origin": "COLAB_STUB",
            "market": "CRYPTO",
        },
        notes=notes,
    )


def colab_cannot_enable_live() -> bool:
    return True


def colab_cannot_submit_orders() -> bool:
    return True
