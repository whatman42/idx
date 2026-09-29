"""Crypto paper execution boundary — aligned with evaluator.

Contract (default, only supported policy):
  Signal_T → Intent (NO FILL at T) → Open_(T+1) × slippage → Ledger

If next bar for the same symbol is missing → NO FILL (not close_T fallback).
Does not touch IDX.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.python.crypto.config import (
    CRYPTO_EXECUTION_POLICY,
    CRYPTO_SLIPPAGE_BPS,
    assert_crypto_paper_only,
    assert_execution_policy,
)


@dataclass(frozen=True)
class FillIntent:
    symbol: str
    signal_timestamp: str
    signal_close: float
    confidence: float = 0.0
    signal_id: str = ""
    strategy_id: str = ""
    strategy_version: str = ""


@dataclass(frozen=True)
class ExecutionResolve:
    status: str
    symbol: str
    signal_timestamp: str
    fill_timestamp: str = ""
    fill_open: float = 0.0
    fill_price: float = 0.0
    slippage_bps: float = 0.0
    execution_policy: str = CRYPTO_EXECUTION_POLICY
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "symbol": self.symbol,
            "signal_timestamp": self.signal_timestamp,
            "fill_timestamp": self.fill_timestamp,
            "fill_open": self.fill_open,
            "fill_price": self.fill_price,
            "slippage_bps": self.slippage_bps,
            "execution_policy": self.execution_policy,
            "reason": self.reason,
            "same_bar_fill": False,
        }


def _buy_px(open_px: float, slip_bps: float) -> float:
    return float(open_px) * (1.0 + float(slip_bps) / 10_000.0)


def resolve_next_bar_open_fill(
    bars: pd.DataFrame,
    *,
    symbol: str,
    signal_timestamp: str,
    slippage_bps: float = CRYPTO_SLIPPAGE_BPS,
) -> ExecutionResolve:
    assert_crypto_paper_only()
    policy = assert_execution_policy()
    if policy != "NEXT_BAR_OPEN":
        return ExecutionResolve(
            status="INVALID",
            symbol=symbol,
            signal_timestamp=str(signal_timestamp),
            reason=f"UNSUPPORTED_POLICY:{policy}",
        )
    if bars is None or bars.empty:
        return ExecutionResolve(
            status="NO_NEXT_BAR",
            symbol=symbol,
            signal_timestamp=str(signal_timestamp),
            reason="EMPTY_BARS",
        )
    g = bars[bars["symbol"].astype(str) == str(symbol)].copy()
    if g.empty:
        return ExecutionResolve(
            status="NO_NEXT_BAR",
            symbol=symbol,
            signal_timestamp=str(signal_timestamp),
            reason="SYMBOL_NOT_IN_BARS",
        )
    g["timestamp"] = pd.to_datetime(g["timestamp"], utc=True, errors="coerce")
    g = g.sort_values("timestamp").reset_index(drop=True)
    sig_ts = pd.to_datetime(signal_timestamp, utc=True, errors="coerce")
    if pd.isna(sig_ts):
        return ExecutionResolve(
            status="INVALID",
            symbol=symbol,
            signal_timestamp=str(signal_timestamp),
            reason="BAD_SIGNAL_TIMESTAMP",
        )
    later = g[g["timestamp"] > sig_ts]
    if later.empty:
        return ExecutionResolve(
            status="NO_NEXT_BAR",
            symbol=symbol,
            signal_timestamp=str(signal_timestamp),
            reason="NO_BAR_AFTER_SIGNAL",
        )
    nxt = later.iloc[0]
    open_col = "open" if "open" in later.columns else "close"
    open_px = float(nxt[open_col])
    if open_px <= 0:
        return ExecutionResolve(
            status="INVALID",
            symbol=symbol,
            signal_timestamp=str(signal_timestamp),
            reason="NON_POSITIVE_OPEN",
        )
    fill_px = _buy_px(open_px, slippage_bps)
    return ExecutionResolve(
        status="READY",
        symbol=symbol,
        signal_timestamp=str(signal_timestamp),
        fill_timestamp=str(nxt["timestamp"]),
        fill_open=open_px,
        fill_price=fill_px,
        slippage_bps=float(slippage_bps),
        execution_policy=policy,
        reason="NEXT_BAR_OPEN",
    )


def intents_from_signals(signals: list[dict[str, Any]]) -> list[FillIntent]:
    out: list[FillIntent] = []
    for s in signals:
        sym = str(s.get("symbol") or "")
        ts = str(s.get("timestamp") or "")
        if not sym or not ts:
            continue
        try:
            ref = float(s.get("price") or s.get("close") or 0.0)
        except (TypeError, ValueError):
            ref = 0.0
        out.append(
            FillIntent(
                symbol=sym,
                signal_timestamp=ts,
                signal_close=ref,
                confidence=float(s.get("confidence") or 0.0),
                signal_id=str(s.get("signal_id") or ""),
                strategy_id=str(s.get("strategy_id") or ""),
                strategy_version=str(s.get("strategy_version") or ""),
            )
        )
    return out
