"""Self-Diagnostics — system health introspection."""
from __future__ import annotations

from typing import Any, Sequence

from src.python.learning.contracts import DriftAlert, HealthReport, SignalEpisode


def diagnose(
    *,
    episodes: Sequence[SignalEpisode] | None = None,
    drift_alerts: Sequence[DriftAlert] | None = None,
    n_failures_observed: int = 0,
    feature_ok: bool = True,
    data_ok: bool = True,
    min_learning_samples: int = 20,
) -> HealthReport:
    warnings: list[str] = []
    details: dict[str, Any] = {}

    data_h = "OK" if data_ok else "FAIL"
    feat_h = "OK" if feature_ok else "FAIL"
    if not data_ok:
        warnings.append("data_health_fail")
    if not feature_ok:
        warnings.append("feature_health_fail")

    model_h = "OK"
    strategy_h = "OK"
    regime_h = "OK"
    for a in drift_alerts or []:
        if a.status == "DEGRADED":
            if a.kind == "PERFORMANCE":
                strategy_h = "WARN"
                warnings.append(f"performance_drift:{a.score:.2f}")
            elif a.kind == "REGIME":
                regime_h = "WARN"
                warnings.append(f"regime_drift:{a.score:.2f}")
            elif a.kind == "MODEL":
                model_h = "WARN"
                warnings.append("model_drift")
            else:
                model_h = "WARN"
        details[f"drift_{a.name}"] = a.to_dict()

    closed = [e for e in (episodes or []) if e.outcome not in ("OPEN", "SKIPPED")]
    learning_h = "OK"
    if len(closed) < min_learning_samples:
        learning_h = "WARN"
        warnings.append("insufficient_learning_samples")

    conf = "OK"
    if strategy_h != "OK" or model_h != "OK":
        conf = "INSUFFICIENT_EVIDENCE"
    if data_h == "FAIL" or feat_h == "FAIL":
        conf = "BLOCKED"

    return HealthReport(
        data_health=data_h,
        feature_health=feat_h,
        model_health=model_h,
        strategy_health=strategy_h,
        regime_health=regime_h,
        execution_health="OK",
        learning_health=learning_h,
        decision_confidence=conf,
        warnings=warnings,
        details=details,
    )
