"""Feature pipeline for evaluator (Phase 2A.1).

OHLCV → build_features → FeatureSnapshot path → Strategy Scorer → signals

Production signal_bot is NOT modified.
"""
from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from src.python.features.engine import build_features
from src.python.features.tiers import FeatureTier
from src.python.strategy.scorers import RuleSMA20Scorer, get_scorer

SignalFn = Callable[[pd.DataFrame], pd.DataFrame]


def signal_fn_from_scorer(
    strategy_id: str = "rule_sma20",
    *,
    max_tier: int = FeatureTier.TIER1_STANDARD,
) -> SignalFn:
    """Build a SignalFn that goes through Feature Engine + scorer (no OHLCV recompute in scorer)."""
    scorer = get_scorer(strategy_id)

    def _fn(bars: pd.DataFrame) -> pd.DataFrame:
        if bars is None or bars.empty:
            return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "score"])
        result = build_features(bars, max_tier=max_tier)
        feat = result.df
        if feat.empty:
            return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "score"])
        # Label isolation: drop labels before scoring
        drop_cols = [c for c in ("y_next_up", "y") if c in feat.columns]
        if drop_cols:
            feat = feat.drop(columns=drop_cols)
        signals = scorer.score_frame(feat)
        return signals

    return _fn


def rule_sma20_feature_signal_fn(*, max_tier: int = FeatureTier.TIER1_STANDARD) -> SignalFn:
    """Control group wired to sma_dist_20 from Feature Engine."""
    return signal_fn_from_scorer("rule_sma20", max_tier=max_tier)
