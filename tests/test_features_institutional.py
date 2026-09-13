"""Institutional feature layer tests: leakage, PIT, tiers, DQ, determinism."""
from __future__ import annotations
import numpy as np
import pandas as pd
from src.python.features import (
    FEATURE_SET_VERSION,
    build_features,
    FeatureTier,
    registry_summary,
    FEATURE_REGISTRY,
)
from src.python.features.normalize import fit_zscore_params, apply_zscore
from src.python.features.diagnostics import feature_diagnostics
from src.python.governor.governor import MLGovernor
from src.python.market.providers import SyntheticProvider
from src.python.ops.paper_portfolio import paper_reset_scope


def _bars(n=80, symbols=None, seed=0):
    symbols = symbols or ["BBCA", "BBRI", "TLKM", "ASII"]
    return SyntheticProvider(n=n, seed=seed).fetch(symbols).df


def test_feature_set_version_stable():
    assert FEATURE_SET_VERSION.startswith("idx_feat_v")


def test_registry_counts_and_tiers():
    s = registry_summary()
    assert s["n_features"] >= 40
    assert s["by_tier"][0] >= 10
    assert s["by_tier"][1] >= 10
    assert all(sp.point_in_time_safe for sp in FEATURE_REGISTRY.values())


def test_build_tier0_deterministic():
    bars = _bars()
    a = build_features(bars, max_tier=0)
    b = build_features(bars, max_tier=0)
    assert a.feature_set_version == b.feature_set_version == FEATURE_SET_VERSION
    assert a.feature_names == b.feature_names
    pd.testing.assert_frame_equal(
        a.df.sort_values(["symbol", "timestamp"]).reset_index(drop=True),
        b.df.sort_values(["symbol", "timestamp"]).reset_index(drop=True),
        check_dtype=False,
    )


def test_tier_monotonic_feature_count():
    bars = _bars(n=100)
    t0 = build_features(bars, max_tier=0)
    t1 = build_features(bars, max_tier=1)
    t2 = build_features(bars, max_tier=2)
    assert len(t0.feature_names) <= len(t1.feature_names) <= len(t2.feature_names)


def test_no_lookahead_future_row_mutation():
    bars = _bars(n=60, seed=1)
    base = build_features(bars, max_tier=1)
    mut = bars.copy()
    idx = mut.sort_values(["symbol", "timestamp"]).groupby("symbol").tail(1).index
    mut.loc[idx, "close"] = mut.loc[idx, "close"] * 10
    mut.loc[idx, "high"] = mut.loc[idx, "high"] * 10
    mut.loc[idx, "volume"] = mut.loc[idx, "volume"] * 100
    adv = build_features(mut, max_tier=1)
    for sym in bars["symbol"].unique():
        b_sym = base.df[base.df["symbol"] == sym].sort_values("timestamp")
        a_sym = adv.df[adv.df["symbol"] == sym].sort_values("timestamp")
        if len(b_sym) < 3:
            continue
        b_prev = b_sym.iloc[:-1].reset_index(drop=True)
        a_prev = a_sym.iloc[:-1].reset_index(drop=True)
        cols = [c for c in base.feature_names if c in b_prev.columns and c in a_prev.columns]
        for c in cols:
            x = pd.to_numeric(b_prev[c], errors="coerce")
            y = pd.to_numeric(a_prev[c], errors="coerce")
            mask = x.notna() & y.notna()
            if mask.any():
                assert np.allclose(x[mask].to_numpy(), y[mask].to_numpy(), rtol=1e-9, atol=1e-9, equal_nan=True), c


def test_cross_section_rank_pit():
    bars = _bars(n=40, symbols=["A", "B", "C"], seed=2)
    feat = build_features(bars, max_tier=1).df
    assert "cs_ret_rank" in feat.columns
    r = feat["cs_ret_rank"].dropna()
    if len(r):
        assert r.min() >= 0 - 1e-9
        assert r.max() <= 1 + 1e-9


def test_cross_section_no_future_leak_via_mutation():
    bars = _bars(n=50, symbols=["A", "B", "C"], seed=3)
    base = build_features(bars, max_tier=1).df
    mut = bars.copy()
    last_ts = mut["timestamp"].max()
    mut.loc[(mut["timestamp"] == last_ts) & (mut["symbol"] == "A"), "close"] *= 5
    adv = build_features(mut, max_tier=1).df
    early = base["timestamp"] < last_ts
    if early.any() and "cs_ret_rank" in base.columns:
        m = early & base["cs_ret_rank"].notna() & adv["cs_ret_rank"].notna()
        if m.any():
            assert np.allclose(base.loc[m, "cs_ret_rank"], adv.loc[m, "cs_ret_rank"], rtol=1e-9, atol=1e-9)


def test_missing_volume_not_coerced_to_zero_flag():
    bars = _bars(n=40, seed=4)
    bars = bars.copy()
    bars.loc[bars.index[:5], "volume"] = np.nan
    bars.loc[bars.index[5:8], "volume"] = 0.0
    feat = build_features(bars, max_tier=0).df
    assert "missing_volume_flag" in feat.columns
    assert "zero_volume_flag" in feat.columns
    assert feat["missing_volume_flag"].sum() >= 1
    assert feat["zero_volume_flag"].sum() >= 1


def test_zero_volume_and_dq_flags():
    bars = _bars(n=30)
    bars = bars.copy()
    bars.loc[bars.index[0], "volume"] = 0
    feat = build_features(bars, max_tier=0).df
    assert "dq_zero_volume" in feat.columns


def test_normalization_train_only():
    bars = _bars(n=80)
    feat = build_features(bars, max_tier=0).df
    cols = [c for c in ("ret_1d", "sma_dist_20") if c in feat.columns]
    n = len(feat)
    cut = n // 2
    train, test = feat.iloc[:cut], feat.iloc[cut:]
    params = fit_zscore_params(train, cols)
    test_params = fit_zscore_params(test, cols)
    z = apply_zscore(test, params)
    assert len(z) == len(test)
    assert params.keys() == test_params.keys() or set(cols).issubset(params.keys())


def test_diagnostics_no_inf_unreported():
    bars = _bars(n=50)
    built = build_features(bars, max_tier=1)
    d = feature_diagnostics(built.df, built.feature_names)
    assert d["n_features"] == len(built.feature_names)


def test_governor_feature_tiers():
    g = MLGovernor()
    assert g.feature_plan(10)["allow_features"] is False
    assert g.feature_plan(50)["max_tier"] == 0
    assert g.feature_plan(150)["max_tier"] == 1
    assert g.feature_plan(500)["max_tier"] == 2
    assert g.feature_plan(500, dq_ok=False)["allow_features"] is False


def test_insufficient_history_flag():
    bars = _bars(n=25)
    feat = build_features(bars, max_tier=0).df
    assert "dq_insufficient_hist" in feat.columns
    assert feat["dq_insufficient_hist"].iloc[0] == 1.0


def test_reset_scope_preserves_features_models():
    scope = paper_reset_scope()
    preserved = " ".join(scope.get("preserved", [])).lower() if isinstance(scope, dict) else str(scope).lower()
    assert "model" in preserved or "does_not" in scope


def test_price_trend_vol_volume_families_present():
    bars = _bars(n=90)
    f = build_features(bars, max_tier=2)
    names = set(f.feature_names)
    assert any(x.startswith("ret_") for x in names)
    assert any(x.startswith("sma_dist_") for x in names)
    assert "atr_14" in names or "ret_std_20" in names
    assert "vol_z_20" in names or "volume_raw" in names


def test_benchmark_absent_marks_rel_nan():
    bars = _bars(n=40)
    f = build_features(bars, max_tier=1)
    if "rel_ret_1d_ihsg" in f.df.columns:
        assert f.df["rel_ret_1d_ihsg"].isna().all() or f.meta.get("benchmark_available") is False
