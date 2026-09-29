"""Crypto FeatureSnapshot PIT + label reject + scorer path."""
from __future__ import annotations

import pytest
import pandas as pd

from src.python.crypto.feature_snapshot import (
    CryptoFeatureSnapshot,
    assert_no_forbidden_feature_names,
    is_forbidden_feature_name,
    snapshots_from_frame,
)
from src.python.crypto.features import assert_pit_no_lookahead, build_crypto_features
from src.python.crypto.scorer import CryptoSma20Scorer, latest_long_signals
from src.python.crypto.strategy import crypto_sma20_signals


def _bars(n: int = 40, sym: str = "BTC/USDT") -> pd.DataFrame:
    rows = []
    px = 100.0
    for i in range(n):
        px *= 1.01 if i % 5 else 0.99
        rows.append(
            {
                "timestamp": f"2026-04-01T{i:02d}:00:00+00:00",
                "symbol": sym,
                "open": px,
                "high": px * 1.01,
                "low": px * 0.99,
                "close": px,
                "volume": 1000.0 + i,
            }
        )
    return pd.DataFrame(rows)


def test_forbidden_names_hard_fail():
    for name in ("y", "Y", "target", "label_foo", "future_ret", "y_next_up"):
        assert is_forbidden_feature_name(name)
    with pytest.raises(ValueError, match="forbidden"):
        CryptoFeatureSnapshot(
            timestamp="t",
            symbol="BTC/USDT",
            features={"sma_dist_20": 0.1, "y_next_up": 1.0},
        )


def test_valid_snapshot_accepts_features():
    snap = CryptoFeatureSnapshot(
        timestamp="t",
        symbol="ETH/USDT",
        features={"sma_dist_20": 0.02, "close": 3000.0},
    )
    assert snap.get("sma_dist_20") == pytest.approx(0.02)


def test_build_features_no_label_columns():
    res = build_crypto_features(_bars())
    cols = set(res.df.columns) - {"timestamp", "symbol"}
    for c in cols:
        assert not is_forbidden_feature_name(c)


def test_pit_row_count():
    bars = _bars(50)
    res = build_crypto_features(bars)
    assert_pit_no_lookahead(bars, res.df)


def test_snapshots_from_frame_skips_labels_auto():
    df = pd.DataFrame(
        {
            "timestamp": ["t1"],
            "symbol": ["X"],
            "sma_dist_20": [0.1],
            "y_next_up": [1.0],
        }
    )
    snaps = snapshots_from_frame(df)
    assert "y_next_up" not in snaps[0].features


def test_scorer_uses_snapshot():
    r = CryptoSma20Scorer().score_row(
        CryptoFeatureSnapshot(
            timestamp="t",
            symbol="BTC/USDT",
            features={"sma_dist_20": 0.05, "close": 100.0},
        )
    )
    assert r["side"] == 1


def test_strategy_default_via_features():
    sigs = crypto_sma20_signals(_bars(50), via_features=True)
    assert isinstance(sigs, list)


def test_latest_long_signals_api():
    assert isinstance(latest_long_signals(_bars(50)), list)
