"""Phase 2B.1 — TrendMultiScorer RESEARCH/SHADOW tests."""
from __future__ import annotations

import inspect
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.python.features.engine import build_features
from src.python.features.registry import FEATURE_REGISTRY
from src.python.strategy.contracts import AlphaScore
from src.python.strategy.evaluator import EvaluatorConfig, evaluate_rule_sma20
from src.python.strategy.feature_pipeline import evaluate_trend_multi
from src.python.strategy.feature_snapshot import FeatureSnapshot
from src.python.strategy.promotion_gate import PromotionGate, PromotionStage
from src.python.strategy.registry import STRATEGY_REGISTRY, get_strategy
from src.python.strategy.scorers import RuleSMA20Scorer, TrendMultiScorer, get_scorer


def _snap(**kwargs) -> FeatureSnapshot:
    base = {
        "sma_dist_20": 0.05,
        "sma_dist_50": 0.03,
        "sma_slope_20": 0.002,
        "trend_persist_20": 0.6,
        "mom_10_21": 0.02,
        "breakout_high_20": 0.01,
        "ema_dist_20": 0.04,
        "regime_trend": 0.5,
        "ret_std_20": 0.02,
        "rel_mom_20_ihsg": 0.01,
    }
    base.update(kwargs)
    return FeatureSnapshot(timestamp="2024-06-15", symbol="AAA", features=base)


def _bars(n: int = 80, symbols=("AAA", "BBB"), seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    ts0 = pd.Timestamp("2024-01-02")
    for si, sym in enumerate(symbols):
        px = 1000.0 + si * 80
        for i in range(n):
            ret = 0.002 + rng.normal(0, 0.008)
            o = px
            c = px * (1 + ret)
            h = max(o, c) * 1.002
            l = min(o, c) * 0.998
            rows.append({
                "timestamp": ts0 + pd.Timedelta(days=i),
                "symbol": sym,
                "open": o, "high": h, "low": l, "close": c,
                "volume": float(rng.integers(1e6, 4e6)),
            })
            px = c
    return pd.DataFrame(rows)


def test_registry_trend_multi_research():
    spec = get_strategy("trend_multi")
    assert spec.status == "RESEARCH"
    assert STRATEGY_REGISTRY["trend_multi"].status == "RESEARCH"
    for f in spec.required_features:
        assert f in FEATURE_REGISTRY


def test_required_features_subset_registry():
    scorer = TrendMultiScorer()
    for f in scorer.required_features:
        assert f in FEATURE_REGISTRY


def test_valid_snapshot_alpha_score():
    scorer = TrendMultiScorer()
    alpha = scorer.to_alpha_score(_snap())
    assert isinstance(alpha, AlphaScore)
    assert alpha.strategy_id == "trend_multi"
    assert alpha.family == "TREND"
    assert math.isfinite(alpha.score)
    assert scorer.score_min <= alpha.score <= scorer.score_max
    assert alpha.regime_compatible is True


def test_missing_required_feature_hard_fail():
    scorer = TrendMultiScorer()
    feats = {
        "sma_dist_20": 0.05,
        "sma_dist_50": 0.03,
        "sma_slope_20": 0.002,
        "trend_persist_20": 0.5,
        "mom_10_21": 0.01,
        "regime_trend": 0.5,
    }
    snap = FeatureSnapshot(timestamp="2024-01-01", symbol="X", features=feats)
    with pytest.raises(KeyError, match="missing required"):
        scorer.score_row(snap)


def test_label_features_hard_fail_on_snapshot():
    for name in ("y", "y_next_up", "target", "future_close"):
        with pytest.raises(ValueError, match="forbidden"):
            FeatureSnapshot(
                timestamp="2024-01-01",
                symbol="X",
                features={"sma_dist_20": 0.1, name: 1.0},
            )


def test_deterministic_identical_twice():
    scorer = TrendMultiScorer()
    snap = _snap()
    a = scorer.score_row(snap)
    b = scorer.score_row(snap)
    assert a["score"] == b["score"]
    assert a["side"] == b["side"]


def test_score_finite_and_range():
    scorer = TrendMultiScorer()
    for kwargs in ({}, {"sma_dist_20": 0.5, "sma_dist_50": 0.4}, {"sma_dist_20": -0.5, "regime_trend": -0.5}):
        r = scorer.score_row(_snap(**kwargs))
        assert math.isfinite(r["score"])
        assert -1.0 <= r["score"] <= 1.0


def test_incompatible_regime_gated():
    scorer = TrendMultiScorer()
    r = scorer.score_row(_snap(regime_trend=0.0))
    assert r["regime_compatible"] is False
    assert r["side"] == 0


def test_compatible_bull_regime_scores():
    scorer = TrendMultiScorer()
    r = scorer.score_row(_snap(regime_trend=0.8, sma_dist_20=0.08))
    assert r["regime_compatible"] is True
    assert r["regime"] == "bull"


def test_nan_required_feature_behavior():
    scorer = TrendMultiScorer()
    with pytest.raises(ValueError, match="non-finite"):
        scorer.score_row(_snap(sma_dist_20=float("nan")))


def test_pit_adversarial_score_at_T():
    bars = _bars(70, symbols=("AAA", "BBB", "CCC"))
    full_feat = build_features(bars, max_tier=1).df
    full_feat["timestamp"] = pd.to_datetime(full_feat["timestamp"])
    counts = full_feat.groupby("timestamp")["symbol"].nunique()
    candidates = counts[counts >= 2].index.sort_values()
    T = candidates[len(candidates) // 2]
    scorer = TrendMultiScorer()
    row_full = full_feat[(full_feat["timestamp"] == T) & (full_feat["symbol"] == "AAA")]
    assert len(row_full) == 1
    feats_full = {
        f: float(row_full.iloc[0][f]) if f in row_full.columns and pd.notna(row_full.iloc[0][f]) else float("nan")
        for f in list(scorer.required_features) + list(scorer.optional_features)
    }
    if any(not math.isfinite(feats_full[f]) for f in scorer.required_features):
        pytest.skip("warm-up NaN at T")
    score_full = scorer.score_row(FeatureSnapshot(timestamp=str(T), symbol="AAA", features=feats_full))["score"]
    trunc = bars[pd.to_datetime(bars["timestamp"]) <= T].copy()
    trunc_feat = build_features(trunc, max_tier=1).df
    trunc_feat["timestamp"] = pd.to_datetime(trunc_feat["timestamp"])
    row_t = trunc_feat[(trunc_feat["timestamp"] == T) & (trunc_feat["symbol"] == "AAA")]
    feats_t = {
        f: float(row_t.iloc[0][f]) if f in row_t.columns and pd.notna(row_t.iloc[0][f]) else float("nan")
        for f in list(scorer.required_features) + list(scorer.optional_features)
    }
    score_t = scorer.score_row(FeatureSnapshot(timestamp=str(T), symbol="AAA", features=feats_t))["score"]
    assert score_full == pytest.approx(score_t, rel=0, abs=1e-12)


def test_no_ohlcv_in_scorer_source():
    src = Path(__file__).resolve().parents[1] / "src/python/strategy/scorers.py"
    text = src.read_text()
    assert "shift(-" not in text
    assert "rolling(" not in text
    src_method = inspect.getsource(TrendMultiScorer.score_row)
    for banned in ('["open"]', "['open']", '["close"]', "['close']", "bars[", "ohlc"):
        assert banned not in src_method


def test_does_not_alter_rule_sma20():
    r = RuleSMA20Scorer().score_row(FeatureSnapshot(
        timestamp="2024-01-01", symbol="Z", features={"sma_dist_20": 0.02}
    ))
    assert r["side"] == 1


def test_evaluator_integration_research():
    bars = _bars(100)
    cfg = EvaluatorConfig(min_trades=1, min_wf_periods=1, wf_train_bars=40, wf_test_bars=15, wf_step_bars=20)
    pkg = evaluate_trend_multi(bars, cfg=cfg)
    assert pkg.strategy_id == "trend_multi"
    assert pkg.signal_defined is True


def test_promotion_gate_still_rejects_incomplete():
    v = PromotionGate().evaluate("trend_multi", {"signal_defined": True})
    assert v.approved is False
    assert v.final_stage != PromotionStage.PROMOTE


def test_get_scorer_trend_multi():
    assert isinstance(get_scorer("trend_multi"), TrendMultiScorer)


def test_rule_sma20_regression_via_features():
    bars = _bars(90)
    cfg = EvaluatorConfig(min_trades=1, min_wf_periods=1, wf_train_bars=40, wf_test_bars=15)
    pkg = evaluate_rule_sma20(bars, cfg=cfg, via_features=True)
    assert pkg.strategy_id == "rule_sma20"
