"""Crypto FeatureSnapshot — SSOT contract for crypto scorers/evaluator.

Scorers MUST accept FeatureSnapshot / feature rows only.
Fail-closed against label-like names (case-insensitive):
  y, y_*, target, target_*, label, label_*, future_*
Domain: CRYPTO only. Does not import IDX FEATURE_REGISTRY.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Protocol, Sequence

import pandas as pd

_FORBIDDEN_EXACT = frozenset({"y", "target", "label"})
_FORBIDDEN_PREFIXES = ("y_", "target_", "label_", "future_")

CRYPTO_FEATURE_SET_VERSION = "crypto_feat_v1"

CRYPTO_FEATURE_REGISTRY: frozenset[str] = frozenset(
    {
        "ret_1",
        "ret_5",
        "sma_dist_10",
        "sma_dist_20",
        "sma_slope_20",
        "vol_z_20",
        "rng_pct",
        "vol_chg_5",
        "close",
    }
)


def is_forbidden_feature_name(name: str) -> bool:
    n = str(name).strip().lower()
    if not n:
        return False
    if n in _FORBIDDEN_EXACT:
        return True
    return any(n.startswith(p) for p in _FORBIDDEN_PREFIXES)


def assert_no_forbidden_feature_names(
    names: Sequence[str], *, context: str = "features"
) -> None:
    bad = [n for n in names if is_forbidden_feature_name(n)]
    if bad:
        raise ValueError(
            f"forbidden label-like names in {context} (hard failure, case-insensitive): {bad}"
        )


@dataclass(frozen=True)
class CryptoFeatureSnapshot:
    timestamp: str
    symbol: str
    features: Mapping[str, float]
    feature_set_version: str = CRYPTO_FEATURE_SET_VERSION
    meta: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert_no_forbidden_feature_names(
            list(self.features.keys()), context="CryptoFeatureSnapshot.features"
        )

    def get(self, name: str, default: float = float("nan")) -> float:
        if is_forbidden_feature_name(name):
            raise ValueError(f"forbidden feature name requested: {name}")
        v = self.features.get(name, default)
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    def require(self, names: Sequence[str]) -> None:
        assert_no_forbidden_feature_names(list(names), context="require")
        missing = [n for n in names if n not in self.features]
        if missing:
            raise KeyError(f"CryptoFeatureSnapshot missing: {missing}")


def assert_required_registered(required: Sequence[str]) -> None:
    assert_no_forbidden_feature_names(list(required), context="required_features")
    unknown = [n for n in required if n not in CRYPTO_FEATURE_REGISTRY]
    if unknown:
        raise ValueError(f"required_features not in CRYPTO_FEATURE_REGISTRY: {unknown}")


def snapshots_from_frame(
    feat_df: pd.DataFrame,
    *,
    feature_set_version: str = CRYPTO_FEATURE_SET_VERSION,
    feature_cols: Optional[Sequence[str]] = None,
) -> list[CryptoFeatureSnapshot]:
    if feat_df is None or feat_df.empty:
        return []
    id_cols = {"timestamp", "symbol"}
    if feature_cols is not None:
        assert_no_forbidden_feature_names(list(feature_cols), context="feature_cols")
        cols = [c for c in feature_cols if c not in id_cols]
    else:
        cols = [
            c
            for c in feat_df.columns
            if c not in id_cols and not is_forbidden_feature_name(c)
        ]
    out: list[CryptoFeatureSnapshot] = []
    for _, row in feat_df.iterrows():
        feats: dict[str, float] = {}
        for c in cols:
            if c not in row.index:
                continue
            try:
                feats[c] = float(row[c]) if pd.notna(row[c]) else float("nan")
            except (TypeError, ValueError):
                feats[c] = float("nan")
        out.append(
            CryptoFeatureSnapshot(
                timestamp=str(row["timestamp"]),
                symbol=str(row["symbol"]),
                features=feats,
                feature_set_version=feature_set_version,
            )
        )
    return out


class CryptoScorer(Protocol):
    strategy_id: str
    required_features: Sequence[str]

    def score_row(self, snap: CryptoFeatureSnapshot) -> dict[str, Any]:
        ...

    def score_frame(self, feat_df: pd.DataFrame) -> pd.DataFrame:
        ...
