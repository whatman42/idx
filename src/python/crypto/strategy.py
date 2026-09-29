"""Crypto strategy namespace — independent of IDX promotion."""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from src.python.crypto.config import assert_crypto_paper_only

STRATEGY_ID = "crypto_rule_sma20"
STRATEGY_VERSION = "crypto_sma_v0"
MARKET = "CRYPTO"


def crypto_sma20_signals(
    bars: pd.DataFrame,
    *,
    lookback: int = 20,
) -> list[dict[str, Any]]:
    """Long when close > SMA(lookback). Research/ops paper path only."""
    assert_crypto_paper_only()
    out: list[dict[str, Any]] = []
    if bars is None or bars.empty:
        return out
    df = bars.sort_values(["symbol", "timestamp"]).copy()
    for sym, g in df.groupby("symbol", sort=False):
        g = g.reset_index(drop=True)
        if len(g) < lookback + 1:
            continue
        close = g["close"].astype(float)
        sma = close.rolling(lookback, min_periods=lookback).mean()
        i = len(g) - 1
        if pd.isna(sma.iloc[i]):
            continue
        if float(close.iloc[i]) > float(sma.iloc[i]):
            dist = float(close.iloc[i] / sma.iloc[i] - 1.0)
            conf = min(0.99, 0.5 + abs(dist) * 5)
            out.append(
                {
                    "symbol": str(sym),
                    "side": "BUY",
                    "price": float(close.iloc[i]),
                    "confidence": conf,
                    "strategy_id": STRATEGY_ID,
                    "strategy_version": STRATEGY_VERSION,
                    "market": MARKET,
                    "quote_currency": "USDT",
                    "timestamp": str(g.iloc[i]["timestamp"]),
                }
            )
    out.sort(key=lambda x: -float(x["confidence"]))
    return out
