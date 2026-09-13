"""Train-only normalization — never fit on full dataset including OOS."""
from __future__ import annotations
from typing import Sequence
import numpy as np
import pandas as pd


def fit_zscore_params(train: pd.DataFrame, cols: Sequence[str]) -> dict[str, dict[str, float]]:
    params = {}
    for c in cols:
        if c not in train.columns:
            continue
        s = pd.to_numeric(train[c], errors="coerce")
        mu = float(s.mean()) if s.notna().any() else 0.0
        sd = float(s.std()) if s.notna().sum() > 1 else 1.0
        if sd == 0 or not np.isfinite(sd):
            sd = 1.0
        params[c] = {"mean": mu, "std": sd}
    return params


def apply_zscore(df: pd.DataFrame, params: dict[str, dict[str, float]]) -> pd.DataFrame:
    out = df.copy()
    for c, p in params.items():
        if c not in out.columns:
            continue
        out[c] = (pd.to_numeric(out[c], errors="coerce") - p["mean"]) / p["std"]
    return out
