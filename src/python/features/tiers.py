from __future__ import annotations
from enum import IntEnum
from src.python.features.registry import FEATURE_REGISTRY


class FeatureTier(IntEnum):
    TIER0_CORE = 0
    TIER1_STANDARD = 1
    TIER2_ADVANCED = 2


def tier_feature_names(max_tier: int | FeatureTier) -> list[str]:
    mt = int(max_tier)
    return sorted(s.name for s in FEATURE_REGISTRY.values() if s.tier <= mt)


def features_for_tier_only(tier: int) -> list[str]:
    return sorted(s.name for s in FEATURE_REGISTRY.values() if s.tier == int(tier))
