"""FeatureSnapshot — official contract between Feature Engine and Strategy Scorers.

Scorers MUST accept FeatureSnapshot / feature rows only.
They MUST NOT recompute indicators from raw OHLCV.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Sequence

import pandas as pd

from src.python.features.registry import FEATURE_REGISTRY


@dataclass(frozen=True)
class FeatureSnapshot:
    """One (timestamp, symbol) feature vector — SSOT input for scorers."""
    timestamp: str
    symbol: str
    features: Mapping[str, float]
    feature_set_version: str = ""
    meta: Mapping[str, Any] = field(default_factory=dict)

    def get(self, name: str, default: float = float("nan")) -> float:
        v = self.features.get(name, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    def require(self, names: Sequence[str]) -> None:
        missing = [n for n in names if n not in self.features]
        if missing:
            raise KeyError(f"FeatureSnapshot missing required features: {missing}")


def assert_required_features_registered(required: Sequence[str]) -> None:
    """Hard failure if strategy asks for unregistered feature names."""
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
    """Convert build_features() output rows into FeatureSnapshot list."""
    if feat_df is None or feat_df.empty:
        return []
    id_cols = {"timestamp", "symbol"}
    label_cols = {"y_next_up", "y"}  # never treat as features
    if feature_cols is None:
        feature_cols = [
            c for c in feat_df.columns
            if c not in id_cols and c not in label_cols
        ]
    else:
        # enforce label isolation even if caller passes them
        feature_cols = [c for c in feature_cols if c not in label_cols]

    out: list[FeatureSnapshot] = []
    for _, row in feat_df.iterrows():
        feats: dict[str, float] = {}
        for c in feature_cols:
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
    """Return X columns only; hard-drop known labels."""
    banned = {"y_next_up", "y"}
    bad = [c for c in feature_cols if c in banned]
    if bad:
        raise ValueError(f"label columns must not enter feature matrix: {bad}")
    cols = [c for c in feature_cols if c in feat_df.columns and c not in banned]
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
