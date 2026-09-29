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


class CryptoMomentumShadowScorer:
    """RESEARCH / SHADOW only — not paper-eligible by default.

    Long when ret_5 > 0 and sma_dist_20 > 0; soft-skip extreme vol_z.
    """

    strategy_id = "crypto_momentum_shadow"
    strategy_version = "crypto_mom_v0"
    plane = "SHADOW"
    required_features: Sequence[str] = ("ret_5", "sma_dist_20", "close")

    def __init__(self) -> None:
        assert_required_registered(list(self.required_features))

    def score_row(self, snap: CryptoFeatureSnapshot) -> dict[str, Any]:
        snap.require(self.required_features)
        ret5 = snap.get("ret_5")
        dist = snap.get("sma_dist_20")
        volz = snap.get("vol_z_20")
        if volz == volz and abs(volz) > 3.0:
            side = 0
            score = 0.0
        elif ret5 == ret5 and dist == dist and ret5 > 0 and dist > 0:
            side = 1
            score = float(ret5) + float(dist)
        else:
            side = 0
            score = float(ret5) if ret5 == ret5 else 0.0
        conf = min(0.99, 0.5 + abs(score) * 3) if side else 0.0
        return {
            "timestamp": snap.timestamp,
            "symbol": snap.symbol,
            "side": side,
            "confidence": float(conf),
            "score": float(score),
            "price": snap.get("close"),
            "market": "CRYPTO",
            "quote_currency": "USDT",
            "strategy_id": self.strategy_id,
            "plane": self.plane,
        }

    def score_frame(self, feat_df: pd.DataFrame) -> pd.DataFrame:
        assert_no_forbidden_feature_names(
            [c for c in feat_df.columns if c not in ("timestamp", "symbol")],
            context="shadow_scorer_frame",
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


_SCORERS = {
    "crypto_rule_sma20": CryptoSma20Scorer,
    "crypto_momentum_shadow": CryptoMomentumShadowScorer,
}


def get_crypto_scorer(strategy_id: str):
    cls = _SCORERS.get(strategy_id)
    if cls is None:
        raise KeyError(f"unknown crypto scorer: {strategy_id}")
    return cls()


def is_shadow_scorer(strategy_id: str) -> bool:
    return strategy_id.endswith("_shadow") or strategy_id == "crypto_momentum_shadow"


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


def latest_executable_long_signals(bars: pd.DataFrame) -> list[dict[str, Any]]:
    """Signal on bar T only when bar T+1 exists (NEXT_BAR_OPEN can resolve)."""
    res = build_crypto_features(bars)
    if res.df.empty:
        return []
    scored = CryptoSma20Scorer().score_frame(res.df)
    if scored.empty:
        return []
    scored = scored.copy()
    scored["timestamp"] = pd.to_datetime(scored["timestamp"], utc=True, errors="coerce")
    out: list[dict[str, Any]] = []
    raw = bars.copy()
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], utc=True, errors="coerce")
    for sym, g in scored.groupby("symbol", sort=False):
        g = g.sort_values("timestamp")
        longs = g[g["side"].astype(int) == 1]
        if longs.empty:
            continue
        chosen = None
        bg = raw[raw["symbol"].astype(str) == str(sym)].sort_values("timestamp")
        for _, row in longs.iloc[::-1].iterrows():
            ts = row["timestamp"]
            later = bg[bg["timestamp"] > ts]
            if later.empty:
                continue
            chosen = row
            break
        if chosen is None:
            continue
        out.append(
            {
                "timestamp": str(chosen["timestamp"]),
                "symbol": str(sym),
                "side": 1,
                "confidence": float(chosen["confidence"]),
                "score": float(chosen["score"]),
                "price": float(chosen["price"]) if pd.notna(chosen["price"]) else None,
                "market": "CRYPTO",
                "quote_currency": "USDT",
            }
        )
    return out
