"""Phase 2A.1.1 — FeatureSnapshot fail-closed label-name guard."""
from __future__ import annotations

import pytest

from src.python.strategy.feature_snapshot import (
    FeatureSnapshot,
    assert_no_forbidden_feature_names,
    assert_required_features_registered,
    feature_matrix_without_labels,
    is_forbidden_feature_name,
    snapshots_from_feature_frame,
)
import pandas as pd


FORBIDDEN_SAMPLES = [
    "y",
    "Y",
    "y_next_up",
    "Y_Next_Up",
    "y_ret_1d",
    "target",
    "Target",
    "target_ret",
    "TARGET_1",
    "label",
    "Label",
    "label_binary",
    "future_ret",
    "FUTURE_close",
    "future_1d",
]

ALLOWED_SAMPLES = [
    "sma_dist_20",
    "ret_1d",
    "cs_mom_rank",
    "regime_trend",
    "vol_z_20",
    "yesterday_gap",  # does not match y / y_* exact or prefix rules? "yesterday_gap".lower().startswith("y_") is False; exact "y" no
]


def test_is_forbidden_patterns():
    for name in FORBIDDEN_SAMPLES:
        assert is_forbidden_feature_name(name), name
    for name in ALLOWED_SAMPLES:
        assert not is_forbidden_feature_name(name), name


def test_snapshot_construction_hard_fails_on_forbidden():
    for name in ("y", "y_next_up", "target", "label", "future_ret", "TARGET_x"):
        with pytest.raises(ValueError, match="forbidden label-like"):
            FeatureSnapshot(
                timestamp="2024-01-01",
                symbol="AAA",
                features={name: 1.0, "sma_dist_20": 0.01},
            )


def test_snapshot_accepts_valid_features():
    snap = FeatureSnapshot(
        timestamp="2024-01-01",
        symbol="AAA",
        features={"sma_dist_20": 0.02, "ret_5d": 0.01},
    )
    assert snap.get("sma_dist_20") == pytest.approx(0.02)


def test_get_rejects_forbidden_name_request():
    snap = FeatureSnapshot(
        timestamp="2024-01-01",
        symbol="AAA",
        features={"sma_dist_20": 0.01},
    )
    with pytest.raises(ValueError, match="forbidden feature name"):
        snap.get("y_next_up")


def test_require_rejects_forbidden_names():
    snap = FeatureSnapshot(
        timestamp="2024-01-01",
        symbol="AAA",
        features={"sma_dist_20": 0.01},
    )
    with pytest.raises(ValueError, match="forbidden"):
        snap.require(["sma_dist_20", "target"])


def test_explicit_feature_cols_hard_fail():
    df = pd.DataFrame({
        "timestamp": ["2024-01-01"],
        "symbol": ["AAA"],
        "sma_dist_20": [0.1],
        "y_next_up": [1.0],
    })
    with pytest.raises(ValueError, match="forbidden label-like"):
        snapshots_from_feature_frame(df, feature_cols=["sma_dist_20", "y_next_up"])


def test_auto_cols_skip_labels_without_putting_in_snapshot():
    """Train frames may still carry y_next_up; auto path excludes them, never packs into snapshot."""
    df = pd.DataFrame({
        "timestamp": ["2024-01-01", "2024-01-02"],
        "symbol": ["AAA", "AAA"],
        "sma_dist_20": [0.1, -0.05],
        "y_next_up": [1.0, 0.0],
        "y": [1.0, 0.0],
    })
    snaps = snapshots_from_feature_frame(df)
    assert len(snaps) == 2
    for s in snaps:
        assert "y_next_up" not in s.features
        assert "y" not in s.features
        assert "sma_dist_20" in s.features


def test_feature_matrix_hard_fail():
    df = pd.DataFrame({"sma_dist_20": [0.1], "target": [1.0]})
    with pytest.raises(ValueError, match="forbidden label-like"):
        feature_matrix_without_labels(df, ["sma_dist_20", "target"])


def test_assert_required_rejects_forbidden_even_if_in_registry_path():
    with pytest.raises(ValueError, match="forbidden"):
        assert_required_features_registered(["y_next_up"])


def test_assert_no_forbidden_direct():
    assert_no_forbidden_feature_names(["sma_dist_20", "ret_1d"])
    with pytest.raises(ValueError):
        assert_no_forbidden_feature_names(["future_return"])
