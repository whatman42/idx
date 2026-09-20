"""Colab research job contracts — expensive compute stays off GitHub Actions.

Jobs are pure specs + validators. Execution happens in Colab notebooks /
src.python.colab.run_training. Never promotes Champion.
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
    budget_sec: int = 1200
    parameters: dict[str, Any] = field(default_factory=dict)
    dataset_hash: str = ""
    feature_hash: str = ""
    status: str = "PENDING"
    result_metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_job(job: ColabResearchJob) -> list[str]:
    """Fail-closed preflight for Colab jobs."""
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
    budget_sec: int = 1200,
    parameters: Optional[dict[str, Any]] = None,
) -> ColabResearchJob:
    kind_s = kind.value if isinstance(kind, ResearchJobKind) else str(kind)
    params = dict(parameters or {})
    job = ColabResearchJob(
        job_id=job_id,
        kind=kind_s,
        experiment_id=experiment_id,
        hypothesis_id=hypothesis_id,
        strategy_id=strategy_id,
        budget_sec=budget_sec,
        parameters=params,
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
    out: list[ColabResearchJob] = []
    for eid in experiment_ids:
        out.append(make_job(
            job_id=f"JOB-{eid}-{kind.value}",
            kind=kind,
            experiment_id=eid,
            budget_sec=budget_sec,
        ))
    return out
