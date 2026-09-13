"""Train-on-history + infer challenger signals (temporal, no shuffle)."""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd

from src.python.ml.families import ModelFamily, FAMILY_SPECS
from src.python.ml.models import _make_estimator
from src.python.features.engine import build_features
from src.python.features.version import FEATURE_SET_VERSION


def _xy_from_feat(feat: pd.DataFrame):
    feat = feat.dropna(subset=["y_next_up"]).reset_index(drop=True)
    num_cols = [
        c for c in feat.columns
        if c not in ("timestamp", "symbol", "y_next_up")
        and pd.api.types.is_numeric_dtype(feat[c])
    ]
    X = feat[num_cols].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = feat["y_next_up"].to_numpy(dtype=int)
    return X, y, num_cols, feat


def train_and_signal(
    bars: pd.DataFrame,
    family: ModelFamily,
    *,
    max_tier: int = 1,
    min_train: int = 40,
) -> dict[str, Any]:
    spec = FAMILY_SPECS[family]
    built = build_features(bars, max_tier=max_tier)
    feat = built.df
    if feat.empty or "y_next_up" not in feat.columns:
        return {
            "model_id": spec.model_id,
            "family": family.value,
            "status": "NO_FEATURES",
            "signals": pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence"]),
            "feature_set_version": FEATURE_SET_VERSION,
        }
    X, y, cols, feat = _xy_from_feat(feat)
    if len(y) < min_train + 5:
        return {
            "model_id": spec.model_id,
            "family": family.value,
            "status": "INSUFFICIENT_ROWS",
            "signals": pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence"]),
            "feature_set_version": FEATURE_SET_VERSION,
            "n_rows": int(len(y)),
        }
    cut = int(len(y) * 0.8)
    cut = max(min_train, min(len(y) - 5, cut))
    est = _make_estimator(family)
    est.fit(X[:cut], y[:cut])
    pred_oos = est.predict(X[cut:])
    acc = float((pred_oos == y[cut:]).mean()) if len(y[cut:]) else 0.0
    last_ts = feat["timestamp"].max()
    last_mask = feat["timestamp"] == last_ts
    X_last = X[last_mask.to_numpy()]
    if len(X_last) == 0:
        return {
            "model_id": spec.model_id,
            "family": family.value,
            "status": "NO_LAST_DAY",
            "signals": pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence"]),
            "feature_set_version": FEATURE_SET_VERSION,
            "metrics": {"accuracy": acc},
        }
    if hasattr(est, "predict_proba"):
        proba = est.predict_proba(X_last)
        classes = list(getattr(est, "classes_", [0, 1]))
        conf = proba[:, classes.index(1)] if 1 in classes else proba[:, -1]
        side = (conf >= 0.5).astype(int)
    else:
        side = est.predict(X_last).astype(int)
        conf = side.astype(float) * 0.6 + 0.2
    sub = feat.loc[last_mask].reset_index(drop=True)
    sig = pd.DataFrame({
        "timestamp": sub["timestamp"].values,
        "symbol": sub["symbol"].astype(str).values,
        "side": side,
        "confidence": conf,
    })
    return {
        "model_id": spec.model_id,
        "family": family.value,
        "status": "OK",
        "signals": sig,
        "feature_set_version": FEATURE_SET_VERSION,
        "feature_names": cols,
        "metrics": {
            "accuracy": acc,
            "expectancy": float(acc - 0.5),
            "n_train": int(cut),
            "n_oos": int(len(y) - cut),
            "train_sec": None,
        },
        "model_meta": {
            "model_id": spec.model_id,
            "family": family.value,
            "feature_set_version": FEATURE_SET_VERSION,
        },
    }
