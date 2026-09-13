from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd


def feature_diagnostics(df: pd.DataFrame, feature_cols: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {"n_rows": len(df), "n_features": len(feature_cols), "features": {}}
    for c in feature_cols:
        if c not in df.columns:
            out["features"][c] = {"status": "MISSING_COLUMN"}
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        n = len(s)
        miss = float(s.isna().mean()) if n else 1.0
        finite = s.replace([np.inf, -np.inf], np.nan)
        n_inf = int(np.isinf(s.to_numpy(dtype=float, copy=True, na_value=np.nan)).sum()) if n else 0
        var = float(finite.var()) if finite.notna().sum() > 1 else 0.0
        out["features"][c] = {
            "missingness": miss,
            "n_inf": n_inf,
            "variance": var,
            "near_zero_variance": var < 1e-12,
            "constant": finite.nunique(dropna=True) <= 1,
        }
    return out
