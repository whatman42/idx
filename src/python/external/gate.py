"""Research readiness & fail-closed promotion on external dependency state.

Required vs optional is per-experiment/job via DependencyReport.required,
not a global plane rule. Colab is required only when the job says so.
"""
from __future__ import annotations

from typing import Any

from src.python.external.states import (
    DependencyStatus,
    ResearchJobDependencyState,
)


CRITICAL_FAIL = frozenset({
    DependencyStatus.UNAVAILABLE.value,
    DependencyStatus.TIMEOUT.value,
    DependencyStatus.AUTH_ERROR.value,
    DependencyStatus.CONFIG_ERROR.value,
    DependencyStatus.NETWORK_ERROR.value,
    DependencyStatus.DATA_INVALID.value,
    DependencyStatus.DATA_STALE.value,
    DependencyStatus.ARTIFACT_MISSING.value,
    DependencyStatus.ARTIFACT_CORRUPT.value,
    DependencyStatus.INTEGRITY_ERROR.value,
    DependencyStatus.UNKNOWN.value,
})


def evaluate_research_job_readiness(
    state: ResearchJobDependencyState,
) -> ResearchJobDependencyState:
    notes: list[str] = list(state.notes)
    required_reports = [
        r for r in (state.data, state.compute, state.artifact, state.memory, state.llm)
        if r.required
    ]
    optional_reports = [
        r for r in (state.data, state.compute, state.artifact, state.memory, state.llm)
        if not r.required
    ]

    blocked = False
    failed = False
    degraded = False

    for r in required_reports:
        if r.status == DependencyStatus.AVAILABLE.value:
            continue
        if r.status in CRITICAL_FAIL or r.status == DependencyStatus.DEGRADED.value:
            blocked = True
            notes.append(f"required_{r.kind}_{r.status}")
            if r.status in (
                DependencyStatus.DATA_INVALID.value,
                DependencyStatus.ARTIFACT_CORRUPT.value,
                DependencyStatus.INTEGRITY_ERROR.value,
            ):
                failed = True

    for r in optional_reports:
        if r.status not in (
            DependencyStatus.AVAILABLE.value,
            DependencyStatus.UNKNOWN.value,
        ):
            degraded = True
            notes.append(f"optional_{r.kind}_{r.status}")

    if failed:
        state.job_status = "FAILED"
    elif blocked:
        state.job_status = "BLOCKED"
    elif degraded:
        state.job_status = "DEGRADED"
    else:
        state.job_status = "SUCCESS"

    state.notes = notes
    return state


def fail_closed_promotion_on_deps(
    state: ResearchJobDependencyState,
    *,
    evidence_ok: bool = False,
) -> dict[str, Any]:
    evaluate_research_job_readiness(state)
    if state.job_status != "SUCCESS" or not evidence_ok:
        return {
            "approved": False,
            "candidacy": False,
            "blocked": True,
            "reason": f"deps_{state.job_status}",
            "job_status": state.job_status,
            "production_mutation": False,
            "dependency_state": state.to_dict(),
        }
    return {
        "approved": False,
        "candidacy": True,
        "blocked": False,
        "reason": "deps_ok_awaiting_authority",
        "job_status": state.job_status,
        "production_mutation": False,
        "dependency_state": state.to_dict(),
    }


def apply_job_requirements(
    state: ResearchJobDependencyState,
    *,
    requires_colab: bool = False,
    requires_memory: bool = False,
    requires_artifact: bool = False,
    requires_llm: bool = False,
    requires_data: bool = True,
) -> ResearchJobDependencyState:
    """Set required flags from experiment policy (per-job, not global)."""
    state.data.required = requires_data
    state.compute.required = requires_colab
    state.memory.required = requires_memory
    state.artifact.required = requires_artifact
    state.llm.required = requires_llm
    return state
