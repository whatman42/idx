"""Crypto scorers — FeatureSnapshot in, signal out."""
from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from src.python.crypto.feature_snapshot import (
    CryptoFeatureSnapshot,
    assert_no_forbidden_feature_names,
    assert_required_registered,
)
from src.python.crypto.features import FEATURE_COLS, build_crypto_features


class CryptoSma20Scorer:
    strategy_id = "crypto_rule_sma20"
    required_features: Sequence[str] = ("sma_dist_20", "close")

    def __init__(self) -> None:
        assert_required_registered(list(self.required_features))

    def score_row(self, snap: CryptoFeatureSnapshot) -> dict[str, Any]:
        snap.require(self.required_features)
        dist = snap.get("sma_dist_20")
        side = 1 if dist == dist and dist > 0 else 0
        conf = min(0.99, 0.5 + abs(dist) * 5) if dist == dist else 0.0
        return {
            "timestamp": snap.timestamp,
            "symbol": snap.symbol,
            "side": side,
            "confidence": float(conf),
            "score": float(dist) if dist == dist else 0.0,
            "price": snap.get("close"),
            "market": "CRYPTO",
            "quote_currency": "USDT",
            "strategy_id": self.strategy_id,
        }

    def score_frame(self, feat_df: pd.DataFrame) -> pd.DataFrame:
        assert_no_forbidden_feature_names(
            [c for c in feat_df.columns if c not in ("timestamp", "symbol")],
            context="scorer_frame",
        )
        rows: list[dict] = []
        for _, row in feat_df.iterrows():
            feats = {
                c: float(row[c]) if c in row.index and pd.notna(row[c]) else float("nan")
                for c in FEATURE_COLS
                if c in feat_df.columns
            }
            snap = CryptoFeatureSnapshot(
                timestamp=str(row["timestamp"]),
                symbol=str(row["symbol"]),
                features=feats,
            )
            rows.append(self.score_row(snap))
        if not rows:
            return pd.DataFrame(
                columns=["timestamp", "symbol", "side", "confidence", "score", "price"]
            )
        return pd.DataFrame(rows)


def crypto_signal_fn_from_features(bars: pd.DataFrame) -> list[dict[str, Any]]:
    res = build_crypto_features(bars)
    if res.df.empty:
        return []
    scored = CryptoSma20Scorer().score_frame(res.df)
    if scored.empty:
        return []
    out: list[dict[str, Any]] = []
    for _, r in scored.iterrows():
        if int(r.get("side") or 0) != 1:
            continue
        out.append(
            {
                "timestamp": str(r["timestamp"]),
                "symbol": str(r["symbol"]),
                "side": 1,
                "confidence": float(r["confidence"]),
                "score": float(r["score"]),
                "price": float(r["price"]) if pd.notna(r["price"]) else None,
                "market": "CRYPTO",
                "quote_currency": "USDT",
            }
        )
    return out


def latest_long_signals(bars: pd.DataFrame) -> list[dict[str, Any]]:
    all_sig = crypto_signal_fn_from_features(bars)
    if not all_sig:
        return []
    by_sym: dict[str, dict] = {}
    for s in all_sig:
        sym = s["symbol"]
        prev = by_sym.get(sym)
        if prev is None or str(s["timestamp"]) >= str(prev["timestamp"]):
            by_sym[sym] = s
    return list(by_sym.values())
