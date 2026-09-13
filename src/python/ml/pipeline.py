"""Governor-driven multi-family lightweight training pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from src.python.governor.governor import MLGovernor, ResourceProfile
from src.python.ml.families import ModelFamily
from src.python.ml.features import build_feature_frame, xy_split
from src.python.ml.models import train_family
from src.python.registry.promotion import evaluate_promotion


def run_lightweight_training(
    bars: pd.DataFrame,
    *,
    out_dir: str | Path = "models/candidates",
    budget_sec: float = 1200.0,
    governor: Optional[MLGovernor] = None,
    families: Optional[Sequence[ModelFamily]] = None,
) -> dict[str, Any]:
    gov = governor or MLGovernor(resources=ResourceProfile.detect())
    gov.resources.training_budget_sec = budget_sec
    plan = gov.training_plan(budget_sec)
    selected = list(families) if families is not None else list(plan.get("families") or [])
    seen = set()
    unique: list[ModelFamily] = []
    for f in selected:
        if isinstance(f, str):
            f = ModelFamily(f)
        if f in seen:
            continue
        seen.add(f)
        unique.append(f)

    report: dict[str, Any] = {
        "status": "RUNNING",
        "plan": plan,
        "families_selected": [f.value for f in unique],
        "results": [],
        "promoted": False,
        "production_unchanged": True,
        "policy": "no_auto_promote_diverse_lightweight",
    }
    if not plan.get("allow_train"):
        report["status"] = "SKIPPED"
        report["reason"] = plan.get("reason") or "budget_too_low"
        return report
    if not unique:
        report["status"] = "SKIPPED"
        report["reason"] = "no_families_selected"
        return report

    from src.python.features.engine import build_features
    from src.python.features.version import FEATURE_SET_VERSION
    fplan = gov.feature_plan(budget_sec, dq_ok=True)
    report["feature_plan"] = fplan
    report["feature_set_version"] = FEATURE_SET_VERSION
    if not fplan.get("allow_features"):
        report["status"] = "SKIPPED"
        report["reason"] = fplan.get("reason", "feature_plan_blocked")
        return report
    max_tier = int(fplan.get("max_tier", 0))
    built = build_features(bars, max_tier=max_tier)
    feat = built.df
    if "y_next_up" not in feat.columns or feat.empty or len(feat) < 50:
        feat = build_feature_frame(bars)
        if feat.empty or len(feat) < 50:
            report["status"] = "DATA_INSUFFICIENT"
            report["reason"] = f"feature_rows={len(feat)}"
            return report
        X, y, _ = xy_split(feat)
        report["feature_source"] = "legacy_ml_features"
    else:
        feat = feat.dropna(subset=["y_next_up"]).reset_index(drop=True)
        num_cols = [
            c for c in built.feature_names
            if c in feat.columns and pd.api.types.is_numeric_dtype(feat[c])
        ]
        if len(num_cols) < 3:
            feat2 = build_feature_frame(bars)
            X, y, _ = xy_split(feat2)
            report["feature_source"] = "legacy_ml_features_fallback"
        else:
            X = feat[num_cols].to_numpy(dtype=float)
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
            y = feat["y_next_up"].to_numpy(dtype=int)
            report["feature_source"] = "institutional_v1"
            report["feature_names_used"] = num_cols
    report["n_rows"] = int(len(y))
    report["n_features"] = int(X.shape[1])

    results = []
    for fam in unique:
        try:
            tr = train_family(fam, X, y, out_dir=out_dir)
            promo = evaluate_promotion(tr.metrics)
            results.append({
                "family": tr.family,
                "model_id": tr.model_id,
                "model_version": tr.model_version,
                "metrics": tr.metrics,
                "path": tr.path,
                "status": tr.status,
                "train_sec": tr.train_sec,
                "promotion_approved": promo.approved,
                "promotion_reason": promo.reason,
            })
        except Exception as e:
            results.append({
                "family": fam.value,
                "status": "TRAIN_FAILED",
                "error": f"{type(e).__name__}: {e}"[:300],
                "promotion_approved": False,
            })
    report["results"] = results
    report["status"] = "TRAINED_NOT_PROMOTED" if results else "EMPTY"
    report["promoted"] = False
    report["production_unchanged"] = True
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "last_training_report.json").write_text(json.dumps(report, indent=2, default=str))
    return report
