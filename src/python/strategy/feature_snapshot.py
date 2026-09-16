"""FeatureSnapshot — official contract between Feature Engine and Strategy Scorers.

Scorers MUST accept FeatureSnapshot / feature rows only.
They MUST NOT recompute indicators from raw OHLCV.

Phase 2A.1.1: fail-closed against label-like names (case-insensitive):
  y, y_*, target, target_*, label, label_*, future_*
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Sequence

import pandas as pd

from src.python.features.registry import FEATURE_REGISTRY

# Exact names (matched case-insensitively)
_FORBIDDEN_EXACT = frozenset({"y", "target", "label"})
# Prefix patterns: y_*, target_*, label_*, future_*
_FORBIDDEN_PREFIXES = ("y_", "target_", "label_", "future_")


def is_forbidden_feature_name(name: str) -> bool:
    """Case-insensitive label/target/future leakage detector."""
    n = str(name).strip().lower()
    if not n:
        return False
    if n in _FORBIDDEN_EXACT:
        return True
    return any(n.startswith(p) for p in _FORBIDDEN_PREFIXES)


def assert_no_forbidden_feature_names(names: Sequence[str], *, context: str = "features") -> None:
    """Hard failure if any name matches the forbidden label patterns."""
    bad = [n for n in names if is_forbidden_feature_name(n)]
    if bad:
        raise ValueError(
            f"forbidden label-like names in {context} (hard failure, case-insensitive): {bad}"
        )


@dataclass(frozen=True)
class FeatureSnapshot:
    """One (timestamp, symbol) feature vector — SSOT input for scorers.

    Construction hard-fails if features contain label-like keys.
    """
    timestamp: str
    symbol: str
    features: Mapping[str, float]
    feature_set_version: str = ""
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert_no_forbidden_feature_names(list(self.features.keys()), context="FeatureSnapshot.features")

    def get(self, name: str, default: float = float("nan")) -> float:
        if is_forbidden_feature_name(name):
            raise ValueError(f"forbidden feature name requested from snapshot: {name}")
        v = self.features.get(name, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    def require(self, names: Sequence[str]) -> None:
        assert_no_forbidden_feature_names(list(names), context="FeatureSnapshot.require")
        missing = [n for n in names if n not in self.features]
        if missing:
            raise KeyError(f"FeatureSnapshot missing required features: {missing}")


def assert_required_features_registered(required: Sequence[str]) -> None:
    """Hard failure if strategy asks for unregistered or forbidden feature names."""
    assert_no_forbidden_feature_names(list(required), context="required_features")
    unknown = [n for n in required if n not in FEATURE_REGISTRY]
    if unknown:
        raise ValueError(
            f"required_features not in FEATURE_REGISTRY (hard failure): {unknown}"
        )


def snapshots_from_feature_frame(
    feat_df: pd.DataFrame,
    *,
    feature_set_version: str = "",
    feature_cols: Optional[Sequence[str]] = None,
) -> list[FeatureSnapshot]:
    """Convert build_features() output rows into FeatureSnapshot list.

    - Explicit feature_cols containing forbidden names → hard failure.
    - Auto column selection skips forbidden names (e.g. y_next_up still on train frames)
      without putting them into the snapshot.
    """
    if feat_df is None or feat_df.empty:
        return []
    id_cols = {"timestamp", "symbol"}

    if feature_cols is not None:
        assert_no_forbidden_feature_names(list(feature_cols), context="feature_cols")
        cols = [c for c in feature_cols if c not in id_cols]
    else:
        cols = [
            c for c in feat_df.columns
            if c not in id_cols and not is_forbidden_feature_name(c)
        ]

    out: list[FeatureSnapshot] = []
    for _, row in feat_df.iterrows():
        feats: dict[str, float] = {}
        for c in cols:
            if c not in row.index:
                continue
            try:
                feats[c] = float(row[c]) if pd.notna(row[c]) else float("nan")
            except (TypeError, ValueError):
                feats[c] = float("nan")
        out.append(FeatureSnapshot(
            timestamp=str(row["timestamp"]),
            symbol=str(row["symbol"]),
            features=feats,
            feature_set_version=feature_set_version,
        ))
    return out


def feature_matrix_without_labels(
    feat_df: pd.DataFrame,
    feature_cols: Sequence[str],
) -> pd.DataFrame:
    """Return X columns only; hard-fail on forbidden label-like names."""
    assert_no_forbidden_feature_names(list(feature_cols), context="feature_matrix")
    cols = [c for c in feature_cols if c in feat_df.columns]
    return feat_df.loc[:, cols].copy()


class StrategyScorer(Protocol):
    """Scorer contract: features in → signal side out. No OHLCV."""

    strategy_id: str
    required_features: Sequence[str]

    def score_row(self, snap: FeatureSnapshot) -> dict[str, Any]:
        """Return dict with at least: side (0|1), confidence (float), score (float)."""
        ...

    def score_frame(self, feat_df: pd.DataFrame) -> pd.DataFrame:
        """Vectorized: input feature frame → signals with timestamp, symbol, side."""
        ...
