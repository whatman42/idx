"""Distinct ML families (one model type per lineage)."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class ModelFamily(str, Enum):
    """One entry per algorithm family — do not add a second boosting/bagging/linear twin."""

    LGBM_BOOST = "LGBM_BOOST"
    RF_BAG = "RF_BAG"
    LOGREG_LINEAR = "LOGREG_LINEAR"
    RULE_SMA = "RULE_SMA"


@dataclass(frozen=True)
class FamilySpec:
    family: ModelFamily
    model_id: str
    display: str
    typical_train_sec: float
    lightweight: bool = True


FAMILY_SPECS: dict[ModelFamily, FamilySpec] = {
    ModelFamily.LGBM_BOOST: FamilySpec(
        ModelFamily.LGBM_BOOST, "idx_lgbm_lw", "LightGBM lightweight", 90.0
    ),
    ModelFamily.RF_BAG: FamilySpec(
        ModelFamily.RF_BAG, "idx_rf_lw", "RandomForest lightweight", 60.0
    ),
    ModelFamily.LOGREG_LINEAR: FamilySpec(
        ModelFamily.LOGREG_LINEAR, "idx_logreg_lw", "LogReg lightweight", 15.0
    ),
}

TRAINABLE_FAMILIES: tuple[ModelFamily, ...] = (
    ModelFamily.LOGREG_LINEAR,
    ModelFamily.RF_BAG,
    ModelFamily.LGBM_BOOST,
)
