"""Crypto risk plane — separate from scorer. Fail-closed. PAPER ONLY."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.python.crypto.config import (
    CRYPTO_MAX_POSITIONS,
    CRYPTO_MAX_WEIGHT,
    assert_crypto_paper_only,
)


@dataclass
class CryptoRiskDecision:
    allowed: bool
    weight: float
    reason: str

    @property
    def allow(self) -> bool:
        """Backward-compatible alias."""
        return self.allowed


def evaluate_crypto_entry(
    *,
    equity_usdt: float,
    open_count: int,
    symbol: str,
    max_positions: int = CRYPTO_MAX_POSITIONS,
    max_weight: float = CRYPTO_MAX_WEIGHT,
    price: Optional[float] = None,
    feature_ok: bool = True,
    data_stale: bool = False,
    universe_ok: bool = True,
    ledger_ok: bool = True,
) -> CryptoRiskDecision:
    assert_crypto_paper_only()
    if not ledger_ok:
        return CryptoRiskDecision(False, 0.0, "LEDGER_INVALID")
    if not feature_ok:
        return CryptoRiskDecision(False, 0.0, "FEATURE_INVALID")
    if data_stale:
        return CryptoRiskDecision(False, 0.0, "DATA_STALE")
    if not universe_ok:
        return CryptoRiskDecision(False, 0.0, "UNIVERSE_UNKNOWN")
    if equity_usdt is None or equity_usdt <= 0:
        return CryptoRiskDecision(False, 0.0, "INVALID_EQUITY")
    if price is not None and float(price) <= 0:
        return CryptoRiskDecision(False, 0.0, "INVALID_PRICE")
    if open_count >= max_positions:
        return CryptoRiskDecision(False, 0.0, "MAX_POSITIONS")
    if not symbol or "/" not in symbol:
        return CryptoRiskDecision(False, 0.0, "FAIL_CLOSED_INVALID_SYMBOL")
    if not str(symbol).endswith("/USDT"):
        return CryptoRiskDecision(False, 0.0, "INVALID_QUOTE")
    w = min(float(max_weight), 0.15)
    if w <= 0:
        return CryptoRiskDecision(False, 0.0, "INVALID_WEIGHT")
    return CryptoRiskDecision(True, w, "ALLOW")
