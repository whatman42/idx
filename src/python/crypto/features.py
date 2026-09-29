"""Crypto Feature Engine — point-in-time only (no look-ahead).

OHLCV at T → features using only data ≤ T.
Labels must never enter CryptoFeatureSnapshot.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.python.crypto.feature_snapshot import (
    CRYPTO_FEATURE_SET_VERSION,
    CryptoFeatureSnapshot,
    assert_no_forbidden_feature_names,
    snapshots_from_frame,
)

FEATURE_COLS = (
    "ret_1",
    "ret_5",
    "sma_dist_10",
    "sma_dist_20",
    "sma_slope_20",
    "vol_z_20",
    "rng_pct",
    "vol_chg_5",
    "close",
)


@dataclass
class CryptoFeatureBuildResult:
    df: pd.DataFrame
    feature_set_version: str = CRYPTO_FEATURE_SET_VERSION
    feature_cols: tuple[str, ...] = FEATURE_COLS


def build_crypto_features(bars: pd.DataFrame) -> CryptoFeatureBuildResult:
    if bars is None or bars.empty:
        return CryptoFeatureBuildResult(df=pd.DataFrame())

    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    parts: list[pd.DataFrame] = []

    for sym, g in df.groupby("symbol", sort=False):
        g = g.sort_values("timestamp").copy()
        c = g["close"].astype(float)
        v = g["volume"].astype(float) if "volume" in g.columns else pd.Series(0.0, index=g.index)
        h = g["high"].astype(float) if "high" in g.columns else c
        low = g["low"].astype(float) if "low" in g.columns else c

        sma10 = c.rolling(10, min_periods=10).mean()
        sma20 = c.rolling(20, min_periods=20).mean()
        sma20_prev = sma20.shift(1)
        vol_ma = v.rolling(20, min_periods=5).mean()
        vol_std = v.rolling(20, min_periods=5).std()

        out = pd.DataFrame(
            {
                "timestamp": g["timestamp"].astype(str).values,
                "symbol": str(sym),
                "ret_1": c.pct_change(1),
                "ret_5": c.pct_change(5),
                "sma_dist_10": (c / sma10 - 1.0),
                "sma_dist_20": (c / sma20 - 1.0),
                "sma_slope_20": (sma20 / sma20_prev - 1.0),
                "vol_z_20": ((v - vol_ma) / vol_std.replace(0, np.nan)).fillna(0.0),
                "rng_pct": ((h - low) / c.replace(0, np.nan)),
                "vol_chg_5": v.pct_change(5).replace([np.inf, -np.inf], np.nan).fillna(0.0),
                "close": c,
            }
        )
        parts.append(out)

    feat = pd.concat(parts, ignore_index=True)
    feat = feat.replace([np.inf, -np.inf], np.nan)
    assert_no_forbidden_feature_names(
        [c for c in feat.columns if c not in ("timestamp", "symbol")],
        context="build_crypto_features",
    )
    return CryptoFeatureBuildResult(df=feat, feature_set_version=CRYPTO_FEATURE_SET_VERSION)


def build_crypto_snapshots(bars: pd.DataFrame) -> list[CryptoFeatureSnapshot]:
    res = build_crypto_features(bars)
    if res.df.empty:
        return []
    return snapshots_from_frame(
        res.df,
        feature_set_version=res.feature_set_version,
        feature_cols=list(FEATURE_COLS),
    )


def assert_pit_no_lookahead(bars: pd.DataFrame, feat: pd.DataFrame) -> None:
    if bars is None or bars.empty or feat is None or feat.empty:
        return
    for sym in feat["symbol"].astype(str).unique():
        n_bars = len(bars[bars["symbol"].astype(str) == sym])
        n_feat = len(feat[feat["symbol"].astype(str) == sym])
        if n_feat > n_bars:
            raise AssertionError(f"PIT_VIOLATION: more feature rows than bars for {sym}")
