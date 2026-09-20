"""Colab research job contracts — expensive compute stays off GitHub Actions.

Jobs are pure specs + validators. Execution happens in Colab / research.wfa_executor.
Never promotes Champion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ResearchJobKind(str, Enum):
    WALK_FORWARD = "WALK_FORWARD"
    HYPEROPT = "HYPEROPT"
    CHALLENGER_TRAIN = "CHALLENGER_TRAIN"
    REGIME_DISCOVERY = "REGIME_DISCOVERY"
    COUNTERFACTUAL_SWEEP = "COUNTERFACTUAL_SWEEP"
    PARAMETER_SWEEP = "PARAMETER_SWEEP"


@dataclass
class ColabResearchJob:
    job_id: str
    kind: str
    experiment_id: str = ""
    hypothesis_id: str = ""
    strategy_id: str = ""
    strategy_version: str = "0.0.0"
    baseline_id: str = "rule_sma20@1.0"
    repository: str = "whatman42/idx"
    commit_sha: str = "UNKNOWN"
    dataset_id: str = "UNKNOWN"
    dataset_hash: str = "UNKNOWN"
    feature_version: str = "UNKNOWN"
    feature_hash: str = "UNKNOWN"
    regime_version: str = "UNKNOWN"
    cost_model: str = "simulation_v2"
    cost_model_id: str = "simulation_v2"
    random_seed: int = 42
    train_start: str = ""
    train_end: str = ""
    validation_start: str = ""
    validation_end: str = ""
    test_start: str = ""
    test_end: str = ""
    execution_timestamp: str = ""
    python_version: str = ""
    dependency_fingerprint: str = "UNKNOWN"
    parameters: dict[str, Any] = field(default_factory=dict)
    search_space: dict[str, Any] = field(default_factory=dict)
    budget_sec: int = 1200
    status: str = "PENDING"
    result_metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def configuration_fingerprint(self) -> str:
        """Material inputs only — never timestamp, path, or UUID."""
        import hashlib, json
        payload = {
            "kind": self.kind,
            "experiment_id": self.experiment_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "baseline_id": self.baseline_id,
            "dataset_hash": self.dataset_hash,
            "feature_hash": self.feature_hash,
            "feature_version": self.feature_version,
            "regime_version": self.regime_version,
            "cost_model": self.cost_model,
            "cost_model_id": self.cost_model_id,
            "random_seed": self.random_seed,
            "parameters": self.parameters,
            "search_space": self.search_space,
            "commit_sha": self.commit_sha,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "validation_start": self.validation_start,
            "validation_end": self.validation_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
        }
        raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()[:24]


def validate_job(job: ColabResearchJob) -> list[str]:
    errs: list[str] = []
    if not job.job_id:
        errs.append("job_id_required")
    if job.kind not in {k.value for k in ResearchJobKind}:
        errs.append(f"unknown_kind:{job.kind}")
    if job.budget_sec <= 0 or job.budget_sec > 7200:
        errs.append("budget_sec_out_of_range")
    if job.kind in (ResearchJobKind.CHALLENGER_TRAIN.value, ResearchJobKind.WALK_FORWARD.value):
        if not job.strategy_id and not job.experiment_id:
            errs.append("strategy_or_experiment_required")
    if job.parameters.get("auto_promote") or job.parameters.get("promote"):
        errs.append("auto_promote_forbidden")
    return errs


def make_job(
    *,
    job_id: str,
    kind: ResearchJobKind | str,
    experiment_id: str = "",
    hypothesis_id: str = "",
    strategy_id: str = "",
    strategy_version: str = "0.0.0",
    baseline_id: str = "rule_sma20@1.0",
    budget_sec: int = 1200,
    parameters: Optional[dict[str, Any]] = None,
    commit_sha: str = "UNKNOWN",
    dataset_hash: str = "UNKNOWN",
    feature_hash: str = "UNKNOWN",
    cost_model: str = "simulation_v2",
    random_seed: int = 42,
) -> ColabResearchJob:
    kind_s = kind.value if isinstance(kind, ResearchJobKind) else str(kind)
    params = dict(parameters or {})
    job = ColabResearchJob(
        job_id=job_id,
        kind=kind_s,
        experiment_id=experiment_id,
        hypothesis_id=hypothesis_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        baseline_id=baseline_id,
        budget_sec=budget_sec,
        parameters=params,
        commit_sha=commit_sha,
        dataset_hash=dataset_hash,
        feature_hash=feature_hash,
        cost_model=cost_model,
        cost_model_id=cost_model,
        random_seed=random_seed,
        notes=["colab_only", "no_auto_promote", "evidence_required"],
    )
    errs = validate_job(job)
    if errs:
        raise ValueError(f"invalid_colab_job:{','.join(errs)}")
    return job


def jobs_from_experiment_ids(
    experiment_ids: list[str],
    *,
    kind: ResearchJobKind = ResearchJobKind.WALK_FORWARD,
    budget_sec: int = 1200,
) -> list[ColabResearchJob]:
    return [
        make_job(
            job_id=f"JOB-{eid}-{kind.value}",
            kind=kind,
            experiment_id=eid,
            budget_sec=budget_sec,
        )
        for eid in experiment_ids
    ]
