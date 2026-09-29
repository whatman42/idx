"""Crypto risk — USDT equity, fail-closed on unknown critical inputs."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.python.crypto.config import CRYPTO_MAX_POSITIONS, CRYPTO_MAX_WEIGHT, assert_crypto_paper_only


@dataclass
class CryptoRiskDecision:
    allow: bool
    weight: float
    reason: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"allow": self.allow, "weight": self.weight, "reason": self.reason, "detail": self.detail}


def evaluate_crypto_entry(
    *,
    equity_usdt: float,
    open_count: int,
    symbol: str,
    price: Optional[float],
    max_weight: float = CRYPTO_MAX_WEIGHT,
    max_positions: int = CRYPTO_MAX_POSITIONS,
) -> CryptoRiskDecision:
    assert_crypto_paper_only()
    if equity_usdt is None or equity_usdt <= 0:
        return CryptoRiskDecision(False, 0.0, "FAIL_CLOSED_UNKNOWN_EQUITY")
    if price is None or price <= 0:
        return CryptoRiskDecision(False, 0.0, "FAIL_CLOSED_UNKNOWN_PRICE")
    if open_count >= max_positions:
        return CryptoRiskDecision(False, 0.0, "MAX_POSITIONS")
    if not symbol or "/" not in symbol:
        return CryptoRiskDecision(False, 0.0, "FAIL_CLOSED_INVALID_SYMBOL")
    w = min(max_weight, 0.15)
    return CryptoRiskDecision(True, w, "ALLOW")
