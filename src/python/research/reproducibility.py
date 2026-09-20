"""End-to-end WFA reproducibility verification.

same commit + dataset_hash + feature_hash + cost_model + seed + parameters
  → equivalent result_hash / metrics (within tolerance)

Any change in those inputs → configuration_fingerprint must change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.python.research.colab_jobs import ColabResearchJob
from src.python.research.experiment_result import ExperimentResult


@dataclass
class ReproReport:
    equivalent: bool
    fingerprint_match: bool
    result_hash_match: bool
    metrics_match: bool
    tolerance: float
    diffs: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "equivalent": self.equivalent,
            "fingerprint_match": self.fingerprint_match,
            "result_hash_match": self.result_hash_match,
            "metrics_match": self.metrics_match,
            "tolerance": self.tolerance,
            "diffs": list(self.diffs),
            "notes": list(self.notes),
        }


def _metric_close(a: Any, b: Any, tol: float) -> bool:
    if a is None and b is None:
        return True
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return a == b


def verify_reproducibility(
    a: ExperimentResult,
    b: ExperimentResult,
    *,
    tolerance: float = 1e-9,
) -> ReproReport:
    diffs: list[str] = []
    notes: list[str] = []
    fp_match = a.configuration_fingerprint == b.configuration_fingerprint
    if not fp_match:
        diffs.append("configuration_fingerprint")
    rh_match = a.result_hash == b.result_hash
    if not rh_match:
        diffs.append("result_hash")

    oos_a = (a.metrics or {}).get("oos") or {}
    oos_b = (b.metrics or {}).get("oos") or {}
    metrics_match = True
    for k in ("n_trades", "expectancy", "total_return", "max_drawdown", "win_rate", "profit_factor"):
        if not _metric_close(oos_a.get(k), oos_b.get(k), tolerance):
            metrics_match = False
            diffs.append(f"oos.{k}")

    if fp_match and a.status != b.status:
        diffs.append("status")
        metrics_match = False

    equivalent = fp_match and rh_match and metrics_match and len(diffs) == 0
    if equivalent:
        notes.append("reproducible_within_tolerance")
    else:
        notes.append("not_equivalent")
    return ReproReport(
        equivalent=equivalent,
        fingerprint_match=fp_match,
        result_hash_match=rh_match,
        metrics_match=metrics_match,
        tolerance=tolerance,
        diffs=diffs,
        notes=notes,
    )


def fingerprint_changes_when_input_changes(
    base: ColabResearchJob,
    *,
    mutate: dict[str, Any],
) -> bool:
    """True if mutating a repro key changes configuration_fingerprint."""
    fp0 = base.configuration_fingerprint()
    for k, v in mutate.items():
        if hasattr(base, k):
            setattr(base, k, v)
        elif k == "parameters":
            base.parameters = dict(v)
        elif k == "random_seed":
            base.random_seed = int(v)
    fp1 = base.configuration_fingerprint()
    return fp0 != fp1
