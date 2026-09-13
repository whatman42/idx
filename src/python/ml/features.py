"""Causal lightweight features for tabular ML (no future leakage)."""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURE_COLS = (
    "ret_1",
    "ret_5",
    "vol_z_20",
    "sma_gap_10",
    "sma_gap_20",
    "rng_pct",
    "vol_chg_5",
)


def build_feature_frame(bars: pd.DataFrame) -> pd.DataFrame:
    if bars is None or bars.empty:
        return pd.DataFrame()
    df = bars.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    parts: list[pd.DataFrame] = []
    for sym, g in df.groupby("symbol", sort=False):
        g = g.sort_values("timestamp").copy()
        c = g["close"].astype(float)
        v = g["volume"].astype(float) if "volume" in g.columns else pd.Series(0.0, index=g.index)
        h = g["high"].astype(float) if "high" in g.columns else c
        low = g["low"].astype(float) if "low" in g.columns else c
        ret_1 = c.pct_change(1)
        ret_5 = c.pct_change(5)
        sma10 = c.rolling(10).mean()
        sma20 = c.rolling(20).mean()
        vol_ma = v.rolling(20).mean()
        vol_std = v.rolling(20).std()
        vol_z = (v - vol_ma) / vol_std.replace(0, np.nan)
        vol_z = vol_z.fillna(0.0)
        vol_chg = v.pct_change(5).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        out = pd.DataFrame(
            {
                "timestamp": g["timestamp"].values,
                "symbol": str(sym),
                "ret_1": ret_1,
                "ret_5": ret_5,
                "vol_z_20": vol_z,
                "sma_gap_10": (c / sma10 - 1.0),
                "sma_gap_20": (c / sma20 - 1.0),
                "rng_pct": ((h - low) / c.replace(0, np.nan)),
                "vol_chg_5": vol_chg,
                "y": (c.shift(-1) / c - 1.0 > 0).astype(float),
            }
        )
        parts.append(out)
    feat = pd.concat(parts, ignore_index=True)
    feat = feat.replace([np.inf, -np.inf], np.nan)
    feat = feat.dropna(subset=list(FEATURE_COLS) + ["y"]).reset_index(drop=True)
    return feat


def xy_split(feat: pd.DataFrame):
    X = feat.loc[:, list(FEATURE_COLS)].to_numpy(dtype=float)
    y = feat["y"].to_numpy(dtype=int)
    return X, y, feat
