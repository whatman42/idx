from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class PromotionReport:
    approved: bool
    reason: str

def evaluate_promotion(metrics: dict[str, Any], *, min_accuracy: float = 0.52,
                       min_expectancy: float = 0.0, max_drawdown: float = 0.25,
                       min_calibration_ok: bool = True) -> PromotionReport:
    acc = float(metrics.get("accuracy", 0) or 0)
    exp = float(metrics.get("expectancy", 0) or 0)
    dd = float(metrics.get("max_drawdown", 1) or 1)
    if acc < min_accuracy:
        return PromotionReport(False, f"accuracy_below_{min_accuracy}")
    if exp < min_expectancy:
        return PromotionReport(False, "expectancy_non_positive")
    if dd > max_drawdown:
        return PromotionReport(False, "drawdown_exceeded")
    return PromotionReport(False, "default_promote_false")
