"""Feature pipeline — shared Feature Engine path for research AND ops.

OHLCV → build_features → FeatureSnapshot path → Strategy Scorer → signals

Ops production uses the same SSOT via ops.production_signal
(PROMOTED scorers only; RESEARCH stays SHADOW).
"""
from __future__ import annotations

from typing import Any, Callable

import pandas as pd

from src.python.features.engine import build_features
from src.python.features.tiers import FeatureTier
from src.python.strategy.scorers import get_scorer

SignalFn = Callable[[pd.DataFrame], pd.DataFrame]


def signal_fn_from_scorer(
    strategy_id: str = "rule_sma20",
    *,
    max_tier: int = FeatureTier.TIER1_STANDARD,
) -> SignalFn:
    scorer = get_scorer(strategy_id)

    def _fn(bars: pd.DataFrame) -> pd.DataFrame:
        if bars is None or bars.empty:
            return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "score"])
        result = build_features(bars, max_tier=max_tier)
        feat = result.df
        if feat.empty:
            return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "score"])
        drop_cols = [c for c in ("y_next_up", "y") if c in feat.columns]
        if drop_cols:
            feat = feat.drop(columns=drop_cols)
        return scorer.score_frame(feat)

    return _fn


def rule_sma20_feature_signal_fn(*, max_tier: int = FeatureTier.TIER1_STANDARD) -> SignalFn:
    return signal_fn_from_scorer("rule_sma20", max_tier=max_tier)


def evaluate_trend_multi(bars: pd.DataFrame, cfg: Any = None):
    """RESEARCH/SHADOW only: trend_multi via Feature Engine + TrendMultiScorer."""
    from src.python.strategy.evaluator import StrategyEvaluator
    from src.python.strategy.registry import get_strategy

    if get_strategy("trend_multi").status != "RESEARCH":
        raise RuntimeError("evaluate_trend_multi blocked: status is not RESEARCH")
    return StrategyEvaluator(cfg).evaluate(
        "trend_multi", bars, signal_fn_from_scorer("trend_multi")
    )
