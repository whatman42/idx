"""Institutional-grade, point-in-time-safe feature library for IDX research/training."""
from src.python.features.version import FEATURE_SET_VERSION
from src.python.features.engine import build_features, FeatureBuildResult
from src.python.features.tiers import FeatureTier, tier_feature_names
from src.python.features.registry import FEATURE_REGISTRY, registry_summary

__all__ = [
    "FEATURE_SET_VERSION",
    "build_features",
    "FeatureBuildResult",
    "FeatureTier",
    "tier_feature_names",
    "FEATURE_REGISTRY",
    "registry_summary",
]
