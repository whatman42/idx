"""Lightweight estimators — one implementation per ModelFamily."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np

from src.python.ml.families import FAMILY_SPECS, ModelFamily


@dataclass
class TrainResult:
    family: str
    model_id: str
    model_version: str
    metrics: dict[str, Any]
    path: str
    status: str
    train_sec: float
    n_train: int
    n_test: int


def _make_estimator(family: ModelFamily):
    if family == ModelFamily.LGBM_BOOST:
        import lightgbm as lgb

        return lgb.LGBMClassifier(
            n_estimators=40,
            max_depth=4,
            num_leaves=15,
            learning_rate=0.08,
            subsample=0.8,
            colsample_bytree=0.8,
            min_child_samples=20,
            n_jobs=1,
            verbosity=-1,
            random_state=42,
        )
    if family == ModelFamily.RF_BAG:
        from sklearn.ensemble import RandomForestClassifier

        return RandomForestClassifier(
            n_estimators=50,
            max_depth=5,
            min_samples_leaf=10,
            max_features="sqrt",
            n_jobs=1,
            random_state=42,
        )
    if family == ModelFamily.LOGREG_LINEAR:
        from sklearn.linear_model import LogisticRegression
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        return Pipeline(
            [
                ("scaler", StandardScaler()),
                (
                    "clf",
                    LogisticRegression(
                        max_iter=200,
                        C=0.5,
                        solver="lbfgs",
                        random_state=42,
                    ),
                ),
            ]
        )
    raise ValueError(f"unsupported family {family}")


def _time_split(X: np.ndarray, y: np.ndarray, test_ratio: float = 0.25):
    n = len(y)
    if n < 40:
        raise ValueError(f"too_few_rows:{n}")
    cut = int(n * (1.0 - test_ratio))
    cut = max(20, min(n - 10, cut))
    return X[:cut], X[cut:], y[:cut], y[cut:]


def train_family(
    family: ModelFamily,
    X: np.ndarray,
    y: np.ndarray,
    *,
    out_dir: str | Path,
    model_version: Optional[str] = None,
) -> TrainResult:
    import time

    spec = FAMILY_SPECS[family]
    t0 = time.monotonic()
    Xtr, Xte, ytr, yte = _time_split(X, y)
    est = _make_estimator(family)
    est.fit(Xtr, ytr)
    pred = est.predict(Xte)
    acc = float((pred == yte).mean()) if len(yte) else 0.0
    hit = float(((pred == 1) & (yte == 1)).sum())
    long_calls = float((pred == 1).sum()) or 1.0
    precision_up = hit / long_calls
    metrics = {
        "accuracy": acc,
        "precision_up": precision_up,
        "expectancy": precision_up - 0.5,
        "max_drawdown": None,
        "n_train": int(len(ytr)),
        "n_test": int(len(yte)),
        "family": family.value,
        "lightweight": True,
    }
    ver = model_version or f"{spec.model_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{ver}.joblib"
    meta_path = out / f"{ver}.meta.json"
    joblib.dump({"estimator": est, "family": family.value, "model_id": spec.model_id}, path)
    meta = {
        "model_version": ver,
        "model_id": spec.model_id,
        "family": family.value,
        "metrics": metrics,
        "promoted": False,
        "production_unchanged": True,
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    elapsed = time.monotonic() - t0
    return TrainResult(
        family=family.value,
        model_id=spec.model_id,
        model_version=ver,
        metrics=metrics,
        path=str(path),
        status="TRAINED_NOT_PROMOTED",
        train_sec=elapsed,
        n_train=int(len(ytr)),
        n_test=int(len(yte)),
    )
