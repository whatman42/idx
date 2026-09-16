"""Strategy scorers — consume FeatureSnapshot only (Phase 2A.1)."""
from __future__ import annotations

from typing import Any, Sequence

import pandas as pd

from src.python.strategy.feature_snapshot import (
    FeatureSnapshot,
    assert_required_features_registered,
)
from src.python.strategy.registry import get_strategy


class RuleSMA20Scorer:
    """Control group: BUY when sma_dist_20 > 0 (from Feature Engine, not recomputed)."""

    strategy_id = "rule_sma20"
    required_features: Sequence[str] = ("sma_dist_20",)

    def __init__(self) -> None:
        assert_required_features_registered(self.required_features)
        # registry contract: required ⊆ FEATURE_REGISTRY already checked
        spec = get_strategy(self.strategy_id)
        if "sma_dist_20" not in spec.required_features and spec.required_features:
            # soft note — registry lists sma_dist_20 for rule_sma20
            pass

    def score_row(self, snap: FeatureSnapshot) -> dict[str, Any]:
        snap.require(self.required_features)
        dist = snap.get("sma_dist_20")
        if dist != dist:  # NaN
            return {
                "side": 0,
                "confidence": 0.0,
                "score": 0.0,
                "symbol": snap.symbol,
                "timestamp": snap.timestamp,
                "strategy_id": self.strategy_id,
                "reason": "sma_dist_20_nan",
            }
        side = 1 if dist > 0.0 else 0
        conf = min(0.99, 0.5 + abs(dist) * 5.0)
        return {
            "side": side,
            "confidence": float(conf),
            "score": float(dist),
            "symbol": snap.symbol,
            "timestamp": snap.timestamp,
            "strategy_id": self.strategy_id,
            "reason": "sma_dist_20_gt_0" if side else "sma_dist_20_le_0",
        }

    def score_frame(self, feat_df: pd.DataFrame) -> pd.DataFrame:
        """feat_df must contain timestamp, symbol, sma_dist_20 from build_features."""
        if feat_df is None or feat_df.empty:
            return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "score", "close"])
        if "sma_dist_20" not in feat_df.columns:
            raise KeyError("score_frame requires sma_dist_20 from Feature Engine")
        if "y_next_up" in feat_df.columns or "y" in feat_df.columns:
            # allow presence in frame but never use for scoring
            pass
        dist = pd.to_numeric(feat_df["sma_dist_20"], errors="coerce")
        side = (dist > 0.0).astype(int)
        side = side.where(dist.notna(), 0)
        conf = (0.5 + dist.abs() * 5.0).clip(upper=0.99).fillna(0.0)
        out = pd.DataFrame({
            "timestamp": pd.to_datetime(feat_df["timestamp"]),
            "symbol": feat_df["symbol"].astype(str),
            "side": side.astype(int),
            "confidence": conf.astype(float),
            "score": dist.fillna(0.0).astype(float),
        })
        if "close" in feat_df.columns:
            out["close"] = pd.to_numeric(feat_df["close"], errors="coerce")
        return out


def get_scorer(strategy_id: str) -> RuleSMA20Scorer:
    if strategy_id == "rule_sma20":
        return RuleSMA20Scorer()
    raise KeyError(f"scorer_not_implemented:{strategy_id}")
