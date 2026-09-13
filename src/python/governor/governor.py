"""Adaptive ML Governor — selects diverse lightweight families and feature tiers under budget."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from src.python.ml.families import FAMILY_SPECS, ModelFamily, TRAINABLE_FAMILIES


@dataclass
class ResourceProfile:
    cpu_count: int = 2
    ram_gb: float = 4.0
    gpu_name: str = ""
    vram_gb: float = 0.0
    training_budget_sec: float = 1200.0

    @classmethod
    def detect(cls) -> "ResourceProfile":
        import os
        return cls(cpu_count=os.cpu_count() or 2)


@dataclass
class MLGovernor:
    """Utility-based selection: never schedules two models from the same family."""

    resources: ResourceProfile = field(default_factory=ResourceProfile.detect)

    def training_plan(self, remaining_sec: float) -> dict[str, Any]:
        remaining = float(remaining_sec)
        if remaining < 30:
            return {
                "allow_train": False,
                "workload": "SKIP",
                "families": [],
                "remaining_sec": remaining,
                "reason": "budget_below_30s",
            }

        ordered = [
            ModelFamily.LOGREG_LINEAR,
            ModelFamily.RF_BAG,
            ModelFamily.LGBM_BOOST,
        ]
        selected: list[str] = []
        cost = 0.0
        for fam in ordered:
            spec = FAMILY_SPECS[fam]
            need = spec.typical_train_sec
            if cost + need <= remaining - 5:
                selected.append(fam.value)
                cost += need

        if not selected and remaining >= 30:
            selected = [ModelFamily.LOGREG_LINEAR.value]
            cost = FAMILY_SPECS[ModelFamily.LOGREG_LINEAR].typical_train_sec

        return {
            "allow_train": bool(selected),
            "workload": "MULTI_FAMILY_LIGHTWEIGHT" if len(selected) > 1 else (
                selected[0] if selected else "SKIP"
            ),
            "families": selected,
            "estimated_train_sec": cost,
            "remaining_sec": remaining,
            "policy": "one_model_per_family",
            "families_available": [f.value for f in TRAINABLE_FAMILIES],
        }

    def feature_plan(self, remaining_sec: float, *, dq_ok: bool = True) -> dict[str, Any]:
        """Select feature tier under budget. Never bypasses DQ hard stop."""
        remaining = float(remaining_sec)
        if not dq_ok:
            return {
                "allow_features": False,
                "max_tier": -1,
                "reason": "dq_blocked",
                "remaining_sec": remaining,
            }
        if remaining < 20:
            return {"allow_features": False, "max_tier": -1, "reason": "budget_too_low", "remaining_sec": remaining}
        if remaining < 90:
            tier = 0
        elif remaining < 300:
            tier = 1
        else:
            tier = 2
        return {
            "allow_features": True,
            "max_tier": tier,
            "tier_name": {0: "TIER0_CORE", 1: "TIER1_STANDARD", 2: "TIER2_ADVANCED"}[tier],
            "remaining_sec": remaining,
            "policy": "adaptive_feature_tier",
            "note": "High hardware does not force max tier",
        }
