"""Crypto strategy namespace — independent of IDX promotion.

Default signal path: OHLCV → Crypto Feature Engine → FeatureSnapshot → Scorer.
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.python.crypto.config import assert_crypto_paper_only

STRATEGY_ID = "crypto_rule_sma20"
STRATEGY_VERSION = "crypto_sma_v0"
MARKET = "CRYPTO"


def crypto_sma20_signals(
    bars: pd.DataFrame,
    *,
    lookback: int = 20,
    via_features: bool = True,
) -> list[dict[str, Any]]:
    assert_crypto_paper_only()
    if bars is None or bars.empty:
        return []

    if via_features:
        from src.python.crypto.scorer import latest_long_signals

        raw = latest_long_signals(bars)
        out: list[dict[str, Any]] = []
        for s in raw:
            px = s.get("price")
            if px is None:
                continue
            out.append(
                {
                    "symbol": str(s["symbol"]),
                    "side": "BUY",
                    "price": float(px),
                    "confidence": float(s.get("confidence") or 0.0),
                    "score": float(s.get("score") or 0.0),
                    "strategy_id": STRATEGY_ID,
                    "strategy_version": STRATEGY_VERSION,
                    "market": MARKET,
                    "quote_currency": "USDT",
                    "timestamp": str(s["timestamp"]),
                    "feature_path": True,
                }
            )
        out.sort(key=lambda x: -float(x["confidence"]))
        return out

    out = []
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
                    "feature_path": False,
                }
            )
    out.sort(key=lambda x: -float(x["confidence"]))
    return out
