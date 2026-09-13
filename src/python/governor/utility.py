"""Deterministic model utility / evidence scoring.

Components (documented weights; sum to 1.0 when all known):
  oos_expectancy   0.30
  profit_factor    0.15
  drawdown         0.20
  stability        0.15
  cost_robustness  0.10
  runtime_eff      0.10

Missing evidence → component contributes neutral via renormalization; all missing → UTILITY_UNKNOWN.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
import math


WEIGHTS = {
    "oos_expectancy": 0.30,
    "profit_factor": 0.15,
    "drawdown": 0.20,
    "stability": 0.15,
    "cost_robustness": 0.10,
    "runtime_eff": 0.10,
}


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def _map_expectancy(e: Optional[float]) -> Optional[float]:
    if e is None:
        return None
    return _clip01((float(e) + 0.5) / 1.0)


def _map_pf(pf: Optional[float]) -> Optional[float]:
    if pf is None:
        return None
    return _clip01(math.tanh((float(pf) - 1.0) / 2.0) * 0.5 + 0.5)


def _map_dd(dd: Optional[float]) -> Optional[float]:
    if dd is None:
        return None
    return _clip01(1.0 - min(abs(float(dd)) / 0.50, 1.0))


def _map_runtime(train_sec: Optional[float], budget: float = 1200.0) -> Optional[float]:
    if train_sec is None:
        return None
    if train_sec <= 0:
        return 1.0
    return _clip01(1.0 - min(float(train_sec) / max(budget, 1.0), 1.0))


@dataclass
class UtilityReport:
    model_id: str
    family: str
    status: str
    score: float
    components: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "family": self.family,
            "status": self.status,
            "score": self.score,
            "components": self.components,
            "reasons": self.reasons,
        }


def score_model_utility(
    *,
    model_id: str,
    family: str,
    metrics: Optional[dict[str, Any]] = None,
    train_sec: Optional[float] = None,
    budget_sec: float = 1200.0,
) -> UtilityReport:
    metrics = metrics or {}
    components: dict[str, Any] = {}
    known = 0
    weighted = 0.0
    weight_sum = 0.0
    reasons: list[str] = []

    mapping = {
        "oos_expectancy": _map_expectancy(metrics.get("expectancy")),
        "profit_factor": _map_pf(metrics.get("profit_factor")),
        "drawdown": _map_dd(metrics.get("max_drawdown")),
        "stability": (
            _clip01(float(metrics["positive_windows"]) / float(metrics["total_windows"]))
            if metrics.get("total_windows")
            else None
        ),
        "cost_robustness": (
            _clip01(float(metrics["cost_survive_ratio"]))
            if metrics.get("cost_survive_ratio") is not None
            else None
        ),
        "runtime_eff": _map_runtime(
            train_sec if train_sec is not None else metrics.get("train_sec"), budget_sec
        ),
    }

    for name, w in WEIGHTS.items():
        val = mapping.get(name)
        if val is None:
            components[name] = {"value": None, "contrib": None, "weight": w, "status": "UNKNOWN"}
            reasons.append(f"{name}:insufficient_evidence")
            continue
        components[name] = {"value": val, "contrib": val * w, "weight": w, "status": "OK"}
        weighted += val * w
        weight_sum += w
        known += 1

    if known == 0:
        return UtilityReport(model_id, family, "UTILITY_UNKNOWN", 0.0, components, reasons + ["no_evidence"])
    score = weighted / weight_sum if weight_sum > 0 else 0.0
    status = "UTILITY_SCORED" if known == len(WEIGHTS) else "UTILITY_PARTIAL"
    if metrics.get("unstable"):
        score *= 0.5
        reasons.append("UNSTABLE_penalty_0.5")
        status = "UTILITY_PARTIAL"
    return UtilityReport(model_id, family, status, float(score), components, reasons)
