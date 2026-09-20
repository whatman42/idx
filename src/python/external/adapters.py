"""Thin adapters that report DependencyReport — never fabricate success."""
from __future__ import annotations

from typing import Any, Optional

from src.python.external.states import (
    DependencyKind,
    DependencyReport,
    DependencyStatus,
    classify_exception,
)
from src.python.memory.client import MemoryStatus, ResearchMemory, get_research_memory


def probe_memory(mem: Optional[ResearchMemory] = None) -> DependencyReport:
    m = mem or get_research_memory()
    if m.status == MemoryStatus.AVAILABLE:
        return DependencyReport(
            kind=DependencyKind.MEMORY.value,
            status=DependencyStatus.AVAILABLE.value,
            required=False,
            message="memory_available",
        )
    if m.status == MemoryStatus.DEGRADED:
        return DependencyReport(
            kind=DependencyKind.MEMORY.value,
            status=DependencyStatus.DEGRADED.value,
            required=False,
            message=m.last_error or "MEMORY_DEGRADED",
        )
    return DependencyReport(
        kind=DependencyKind.MEMORY.value,
        status=DependencyStatus.UNAVAILABLE.value,
        required=False,
        message=m.last_error or "MEMORY_UNAVAILABLE",
    )


def probe_colab_available() -> DependencyReport:
    import os
    is_colab = os.path.exists("/content") or bool(
        os.getenv("COLAB_RELEASE_TAG") or os.getenv("COLAB_GPU")
    )
    if is_colab:
        return DependencyReport(
            kind=DependencyKind.COMPUTE.value,
            status=DependencyStatus.AVAILABLE.value,
            required=False,
            message="colab_runtime_detected",
        )
    return DependencyReport(
        kind=DependencyKind.COMPUTE.value,
        status=DependencyStatus.UNAVAILABLE.value,
        required=False,
        message="colab_runtime_not_detected",
        meta={"fallback": "QUEUE_OR_BLOCK_IF_REQUIRES_COLAB_NO_HEAVY_ON_ACTIONS"},
    )


def report_colab_job_outcome(
    *,
    completed: bool,
    timeout: bool = False,
    artifact_present: bool = False,
    result_hash: str = "",
    error: str = "",
) -> DependencyReport:
    if timeout:
        return DependencyReport(
            kind=DependencyKind.COMPUTE.value,
            status=DependencyStatus.TIMEOUT.value,
            required=False,
            message=error or "colab_timeout",
            can_retry=True,
        )
    if not completed:
        return DependencyReport(
            kind=DependencyKind.COMPUTE.value,
            status=DependencyStatus.UNAVAILABLE.value,
            required=False,
            message=error or "colab_incomplete",
        )
    if not artifact_present or not result_hash:
        return DependencyReport(
            kind=DependencyKind.COMPUTE.value,
            status=DependencyStatus.ARTIFACT_MISSING.value,
            required=False,
            message="colab_output_missing_or_unhashed",
        )
    return DependencyReport(
        kind=DependencyKind.COMPUTE.value,
        status=DependencyStatus.AVAILABLE.value,
        required=False,
        message="colab_completed",
        meta={"result_hash_present": True},
    )


def probe_drive_artifact(
    *,
    available: bool = False,
    checksum_ok: Optional[bool] = None,
    auth_ok: bool = True,
    error: str = "",
) -> DependencyReport:
    if not auth_ok:
        return DependencyReport(
            kind=DependencyKind.ARTIFACT.value,
            status=DependencyStatus.AUTH_ERROR.value,
            required=False,
            message=error or "drive_auth_failure",
        )
    if not available:
        return DependencyReport(
            kind=DependencyKind.ARTIFACT.value,
            status=DependencyStatus.ARTIFACT_MISSING.value,
            required=False,
            message=error or "ARTIFACT_UNAVAILABLE",
        )
    if checksum_ok is False:
        return DependencyReport(
            kind=DependencyKind.ARTIFACT.value,
            status=DependencyStatus.ARTIFACT_CORRUPT.value,
            required=False,
            message="drive_checksum_mismatch",
        )
    return DependencyReport(
        kind=DependencyKind.ARTIFACT.value,
        status=DependencyStatus.AVAILABLE.value,
        required=False,
        message="artifact_ok",
    )


def probe_llm(*, available: bool = False, error: str = "") -> DependencyReport:
    if available:
        return DependencyReport(
            kind=DependencyKind.LLM.value,
            status=DependencyStatus.AVAILABLE.value,
            required=False,
            message="llm_available",
        )
    return DependencyReport(
        kind=DependencyKind.LLM.value,
        status=DependencyStatus.UNAVAILABLE.value,
        required=False,
        message=error or "LLM_UNAVAILABLE",
        meta={"numeric_truth": False, "fabricated": False},
    )


def probe_market_data(
    *,
    rows: int = 0,
    stale: bool = False,
    invalid: bool = False,
    error: str = "",
) -> DependencyReport:
    if invalid or rows <= 0:
        return DependencyReport(
            kind=DependencyKind.DATA.value,
            status=DependencyStatus.DATA_INVALID.value,
            required=True,
            message=error or "invalid_or_empty_ohlcv",
        )
    if stale:
        return DependencyReport(
            kind=DependencyKind.DATA.value,
            status=DependencyStatus.DATA_STALE.value,
            required=True,
            message=error or "stale_market_data",
        )
    return DependencyReport(
        kind=DependencyKind.DATA.value,
        status=DependencyStatus.AVAILABLE.value,
        required=True,
        message=f"bars={rows}",
    )


def safe_external_call(fn, *, kind: DependencyKind, required: bool = False) -> tuple[Any, DependencyReport]:
    try:
        out = fn()
        return out, DependencyReport(
            kind=kind.value,
            status=DependencyStatus.AVAILABLE.value,
            required=required,
            message="ok",
        )
    except Exception as e:
        rep = classify_exception(e, kind=kind)
        rep.required = required
        return None, rep
