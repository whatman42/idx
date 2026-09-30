"""Immutable crypto signal contract — intent only, never a fill."""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Optional

from src.python.crypto.config import (
    CRYPTO_EXECUTION_POLICY,
    CRYPTO_FEATURE_VERSION,
    CRYPTO_STRATEGY_ID,
    CRYPTO_STRATEGY_VERSION,
    assert_crypto_paper_only,
)


def _signal_id(
    *,
    cycle_id: str,
    symbol: str,
    strategy_id: str,
    signal_timestamp: str,
    side: str,
) -> str:
    raw = f"{cycle_id}|{symbol}|{strategy_id}|{signal_timestamp}|{side}"
    return "sig_" + hashlib.sha256(raw.encode()).hexdigest()[:24]


@dataclass(frozen=True)
class CryptoSignal:
    signal_id: str
    cycle_id: str
    symbol: str
    strategy_id: str
    strategy_version: str
    feature_version: str
    signal_timestamp: str
    signal_side: str
    reference_price: float
    execution_policy: str
    executable_at: str
    confidence: float = 0.0
    source: str = "crypto_paper_ops"
    contract_version: str = "crypto_signal_v1"
    feature_snapshot_ref: str = ""
    risk_meta: Optional[dict] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["is_fill"] = False
        d["live_execution"] = False
        return d


def build_signal(
    *,
    cycle_id: str,
    symbol: str,
    signal_timestamp: str,
    side: str = "BUY",
    reference_price: float,
    confidence: float = 0.0,
    strategy_id: str = CRYPTO_STRATEGY_ID,
    strategy_version: str = CRYPTO_STRATEGY_VERSION,
    feature_version: str = CRYPTO_FEATURE_VERSION,
    risk_meta: Optional[dict] = None,
    feature_snapshot_ref: str = "",
) -> CryptoSignal:
    assert_crypto_paper_only()
    side_u = str(side).upper()
    if side_u not in ("BUY", "SELL"):
        raise ValueError(f"INVALID_SIGNAL_SIDE:{side}")
    if reference_price is None or float(reference_price) <= 0:
        raise ValueError("INVALID_REFERENCE_PRICE")
    sid = _signal_id(
        cycle_id=cycle_id,
        symbol=symbol,
        strategy_id=strategy_id,
        signal_timestamp=str(signal_timestamp),
        side=side_u,
    )
    return CryptoSignal(
        signal_id=sid,
        cycle_id=cycle_id,
        symbol=symbol,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        feature_version=feature_version,
        signal_timestamp=str(signal_timestamp),
        signal_side=side_u,
        reference_price=float(reference_price),
        execution_policy=CRYPTO_EXECUTION_POLICY,
        executable_at="T+1_OPEN",
        confidence=float(confidence or 0.0),
        feature_snapshot_ref=feature_snapshot_ref or "",
        risk_meta=risk_meta or {},
    )
