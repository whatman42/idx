"""Experiment Manager + immutable Experiment Ledger."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from src.python.learning.contracts import ExperimentSpec, Hypothesis, LearningStatus
from src.python.strategy.promotion_gate import evaluate_for_candidacy


class ExperimentLedger:
    """Append-only experiment history. Never mutate past EXP rows."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self._rows: list[ExperimentSpec] = []
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        data = json.loads(self.path.read_text())
        for row in data.get("experiments", []):
            self._rows.append(ExperimentSpec(**{
                k: row[k] for k in ExperimentSpec.__dataclass_fields__ if k in row
            }))

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(
            {"experiments": [e.to_dict() for e in self._rows], "immutable": True},
            indent=2,
        ))

    def ids(self) -> set[str]:
        return {e.experiment_id for e in self._rows}

    def register(self, spec: ExperimentSpec) -> ExperimentSpec:
        if spec.experiment_id in self.ids():
            raise RuntimeError(f"immutable_violation experiment_id={spec.experiment_id}")
        self._rows.append(spec)
        self._save()
        return spec

    def update_metrics(self, experiment_id: str, metrics: dict[str, Any], status: str) -> ExperimentSpec:
        for e in self._rows:
            if e.experiment_id == experiment_id:
                e.metrics = dict(metrics)
                e.status = status
                e.notes = list(e.notes) + [f"metrics_updated status={status}"]
                self._save()
                return e
        raise KeyError(experiment_id)

    def list_all(self) -> list[ExperimentSpec]:
        return list(self._rows)


def build_experiment_from_hypothesis(
    h: Hypothesis,
    *,
    experiment_id: str,
    name: str,
    challenger_strategy_id: str,
    challenger_version: str,
    parameters: Optional[dict[str, Any]] = None,
    dataset_hash: str = "",
    feature_hash: str = "",
) -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id=experiment_id,
        hypothesis_id=h.hypothesis_id,
        name=name,
        challenger_strategy_id=challenger_strategy_id,
        challenger_version=challenger_version,
        dataset_hash=dataset_hash,
        feature_hash=feature_hash,
        parameters=parameters or {},
        status=LearningStatus.EXPERIMENT.value,
    )


def evaluate_experiment_to_candidacy(
    experiment: ExperimentSpec,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Run PromotionGate on experiment evidence — at most CANDIDATE, never auto-PROMOTED."""
    evidence = dict(evidence)
    evidence.setdefault("strategy_id", experiment.challenger_strategy_id or experiment.name)
    evidence.setdefault("strategy_version", experiment.challenger_version)
    evidence.setdefault("evidence_id", f"EP-{experiment.experiment_id}")
    evidence.setdefault("dataset_hash", experiment.dataset_hash)
    evidence.setdefault("feature_hash", experiment.feature_hash)
    evidence.setdefault("cost_model", experiment.cost_model)
    decision = evaluate_for_candidacy(str(evidence["strategy_id"]), evidence)
    return {
        "experiment_id": experiment.experiment_id,
        "lifecycle_status": decision.lifecycle_status,
        "candidacy": decision.candidacy,
        "approved": decision.approved,
        "reason": decision.reason,
        "decision": decision.to_dict(),
    }
