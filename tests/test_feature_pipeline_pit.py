"""Phase 2A.1 acceptance: FeatureSnapshot, PIT, label isolation, norm, registry, SMA20 wire."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.python.features.engine import build_features
from src.python.features.normalize import apply_zscore, fit_zscore_params
from src.python.features.registry import FEATURE_REGISTRY
from src.python.features.tiers import FeatureTier
from src.python.strategy.evaluator import EvaluatorConfig, evaluate_rule_sma20
from src.python.strategy.feature_pipeline import rule_sma20_feature_signal_fn
from src.python.strategy.feature_snapshot import (
    assert_required_features_registered,
    feature_matrix_without_labels,
    snapshots_from_feature_frame,
)
from src.python.strategy.registry import STRATEGY_REGISTRY, list_strategies
from src.python.strategy.scorers import RuleSMA20Scorer


def _bars(n: int = 80, symbols=("AAA", "BBB"), seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    ts0 = pd.Timestamp("2024-01-02")
    for si, sym in enumerate(symbols):
        px = 1000.0 + si * 100
        for i in range(n):
            ret = 0.0015 + rng.normal(0, 0.008)
            o = px
            c = px * (1 + ret)
            h = max(o, c) * 1.002
            l = min(o, c) * 0.998
            rows.append({
                "timestamp": ts0 + pd.Timedelta(days=i),
                "symbol": sym,
                "open": o, "high": h, "low": l, "close": c,
                "volume": float(rng.integers(1e6, 5e6)),
            })
            px = c
    return pd.DataFrame(rows)


def test_registry_required_features_subset_of_feature_registry():
    for spec in list_strategies():
        for f in spec.required_features:
            assert f in FEATURE_REGISTRY, f"{spec.strategy_id} requires unregistered {f}"


def test_assert_required_features_hard_failure():
    with pytest.raises(ValueError, match="not in FEATURE_REGISTRY":
        assert_required_features_registered(["not_a_real_feature_xyz"])


def test_feature_snapshot_excludes_labels():
    bars = _bars(50)
    res = build_features(bars, max_tier=FeatureTier.TIER1_STANDARD)
    snaps = snapshots_from_feature_frame(res.df, feature_set_version=res.feature_set_version)
    assert snaps
    for s in snaps[:5]:
        assert "y_next_up" not in s.features
        assert "y" not in s.features


def test_label_isolation_feature_matrix_raises():
    df = pd.DataFrame({"sma_dist_20": [0.1], "y_next_up": [1.0]})
    with pytest.raises(ValueError, match="forbidden label-like"):
        feature_matrix_without_labels(df, ["sma_dist_20", "y_next_up"])


def test_rule_sma20_scorer_uses_sma_dist_20_only():
    scorer = RuleSMA20Scorer()
    assert "sma_dist_20" in scorer.required_features
    bars = _bars(40)
    res = build_features(bars, max_tier=1)
    feat = res.df.drop(columns=[c for c in ("y_next_up", "y") if c in res.df.columns])
    sig = scorer.score_frame(feat)
    assert set(["timestamp", "symbol", "side"]).issubset(sig.columns)
    merged = feat.merge(sig, on=["timestamp", "symbol"], suffixes=("_f", ""))
    if not merged.empty and "sma_dist_20" in merged.columns:
        m = merged.dropna(subset=["sma_dist_20"])
        if len(m):
            agree = ((m["sma_dist_20"] > 0) & (m["side"] == 1)) | ((m["sma_dist_20"] <= 0) & (m["side"] == 0))
            assert agree.all()


def test_pit_adversarial_truncate_future():
    """For timestamp T, wiping bars after T must not change features at T."""
    bars = _bars(60, symbols=("AAA", "BBB", "CCC"))
    full = build_features(bars, max_tier=1).df
    full["timestamp"] = pd.to_datetime(full["timestamp"])
    counts = full.groupby("timestamp")["symbol"].nunique()
    candidates = counts[counts >= 2].index.sort_values()
    assert len(candidates) > 10
    T = candidates[len(candidates) // 2]

    check_cols = [
        c for c in (
            "sma_dist_20", "ema_dist_20", "ret_5d", "ret_20d", "mom_accel_5",
            "ret_std_20", "vol_z_20", "natr_14", "trend_persist_20",
            "cs_mom_rank", "cs_ret_rank", "regime_vol", "regime_trend",
        )
        if c in full.columns
    ]
    assert len(check_cols) >= 5

    row_full = full[full["timestamp"] == T].sort_values("symbol").reset_index(drop=True)
    truncated = bars[pd.to_datetime(bars["timestamp"]) <= T].copy()
    trunc_feat = build_features(truncated, max_tier=1).df
    trunc_feat["timestamp"] = pd.to_datetime(trunc_feat["timestamp"])
    row_trunc = trunc_feat[trunc_feat["timestamp"] == T].sort_values("symbol").reset_index(drop=True)

    assert len(row_full) == len(row_trunc)
    for col in check_cols:
        a = pd.to_numeric(row_full[col], errors="coerce").to_numpy()
        b = pd.to_numeric(row_trunc[col], errors="coerce").to_numpy()
        both = np.isfinite(a) & np.isfinite(b)
        if both.any():
            np.testing.assert_allclose(a[both], b[both], rtol=1e-9, atol=1e-12, err_msg=col)


def test_normalization_fit_train_only():
    bars = _bars(100)
    feat = build_features(bars, max_tier=0).df
    cols = [c for c in ("ret_1d", "sma_dist_20", "ret_5d") if c in feat.columns]
    assert cols
    n = len(feat)
    train = feat.iloc[: n // 2]
    test = feat.iloc[n // 2 :]
    params = fit_zscore_params(train, cols)
    tr = apply_zscore(train, params)
    assert not tr[cols].isna().all().all()
    for c in cols:
        mu = tr[c].mean()
        if np.isfinite(mu):
            assert abs(mu) < 0.15


def test_evaluate_rule_sma20_via_features_default():
    bars = _bars(100)
    cfg = EvaluatorConfig(min_trades=3, min_wf_periods=1, wf_train_bars=40, wf_test_bars=15, wf_step_bars=20)
    pkg = evaluate_rule_sma20(bars, cfg=cfg, via_features=True)
    assert pkg.strategy_id == "rule_sma20"
    assert pkg.signal_defined is True


def test_baseline_reconciliation_legacy_vs_features():
    bars = _bars(80)
    from src.python.strategy.evaluator import sma20_signal_fn
    leg = sma20_signal_fn(20)(bars)
    feat_sig = rule_sma20_feature_signal_fn()(bars)
    if leg.empty or feat_sig.empty:
        pytest.skip("no signals")
    m = leg.merge(feat_sig, on=["timestamp", "symbol"], suffixes=("_legacy", "_feat"))
    if m.empty:
        pytest.skip("no overlap")
    agree = (m["side_legacy"] == m["side_feat"]).mean()
    assert agree >= 0.7, f"agreement {agree:.2%} too low — investigate definition drift"


def test_feature_signal_fn_does_not_pass_labels_to_scorer():
    bars = _bars(40)
    sig = rule_sma20_feature_signal_fn()(bars)
    assert "y_next_up" not in sig.columns
    assert "y" not in sig.columns
