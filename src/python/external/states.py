"""Canonical external dependency status codes."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class DependencyStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    TIMEOUT = "TIMEOUT"
    AUTH_ERROR = "AUTH_ERROR"
    CONFIG_ERROR = "CONFIG_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    DATA_INVALID = "DATA_INVALID"
    DATA_STALE = "DATA_STALE"
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    ARTIFACT_CORRUPT = "ARTIFACT_CORRUPT"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    UNKNOWN = "UNKNOWN"


class DependencyKind(str, Enum):
    MEMORY = "MEMORY"
    ARTIFACT = "ARTIFACT"
    COMPUTE = "COMPUTE"
    LLM = "LLM"
    DATA = "DATA"
    GITHUB = "GITHUB"
    OTHER = "OTHER"


TRANSIENT = frozenset({
    DependencyStatus.TIMEOUT,
    DependencyStatus.NETWORK_ERROR,
    DependencyStatus.DEGRADED,
})
PERMANENT = frozenset({
    DependencyStatus.AUTH_ERROR,
    DependencyStatus.CONFIG_ERROR,
    DependencyStatus.DATA_INVALID,
    DependencyStatus.ARTIFACT_CORRUPT,
    DependencyStatus.INTEGRITY_ERROR,
})


@dataclass
class DependencyReport:
    kind: str
    status: str
    required: bool = False
    message: str = ""
    error_type: str = ""
    can_retry: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        safe_meta = {
            k: v for k, v in (self.meta or {}).items()
            if not any(s in k.lower() for s in ("token", "secret", "password", "api_key", "credential"))
        }
        d["meta"] = safe_meta
        return d

    @property
    def ok(self) -> bool:
        return self.status == DependencyStatus.AVAILABLE.value


def classify_exception(exc: BaseException, *, kind: DependencyKind = DependencyKind.OTHER) -> DependencyReport:
    name = type(exc).__name__
    msg = str(exc)[:200]
    for bad in ("token=", "Bearer ", "api_key=", "password="):
        if bad.lower() in msg.lower():
            msg = f"{name}:[redacted]"
            break

    status = DependencyStatus.UNAVAILABLE
    can_retry = False
    low = (name + " " + msg).lower()
    if "timeout" in low or name in ("TimeoutError", "ReadTimeout", "ConnectTimeout"):
        status = DependencyStatus.TIMEOUT
        can_retry = True
    elif "auth" in low or "unauthorized" in low or "401" in low or "403" in low:
        status = DependencyStatus.AUTH_ERROR
        can_retry = False
    elif "network" in low or "connection" in low or name in ("ConnectionError", "URLError"):
        status = DependencyStatus.NETWORK_ERROR
        can_retry = True
    elif "config" in low or "missing env" in low:
        status = DependencyStatus.CONFIG_ERROR
        can_retry = False
    elif "stale" in low:
        status = DependencyStatus.DATA_STALE
        can_retry = False
    elif "corrupt" in low or "checksum" in low:
        status = DependencyStatus.ARTIFACT_CORRUPT
        can_retry = False
    elif "not found" in low or "404" in low or "missing" in low:
        status = DependencyStatus.ARTIFACT_MISSING
        can_retry = False

    return DependencyReport(
        kind=kind.value,
        status=status.value,
        message=msg,
        error_type=name,
        can_retry=can_retry,
    )


@dataclass
class ResearchJobDependencyState:
    data: DependencyReport = field(default_factory=lambda: DependencyReport(
        kind=DependencyKind.DATA.value, status=DependencyStatus.UNKNOWN.value, required=True,
    ))
    memory: DependencyReport = field(default_factory=lambda: DependencyReport(
        kind=DependencyKind.MEMORY.value, status=DependencyStatus.UNKNOWN.value, required=False,
    ))
    compute: DependencyReport = field(default_factory=lambda: DependencyReport(
        kind=DependencyKind.COMPUTE.value, status=DependencyStatus.UNKNOWN.value, required=True,
    ))
    artifact: DependencyReport = field(default_factory=lambda: DependencyReport(
        kind=DependencyKind.ARTIFACT.value, status=DependencyStatus.UNKNOWN.value, required=False,
    ))
    llm: DependencyReport = field(default_factory=lambda: DependencyReport(
        kind=DependencyKind.LLM.value, status=DependencyStatus.UNKNOWN.value, required=False,
    ))
    job_status: str = "UNKNOWN"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.data.to_dict(),
            "memory": self.memory.to_dict(),
            "compute": self.compute.to_dict(),
            "artifact": self.artifact.to_dict(),
            "llm": self.llm.to_dict(),
            "job_status": self.job_status,
            "notes": list(self.notes),
            "can_promote": self.job_status == "SUCCESS",
            "affects_ledger": False,
            "affects_champion": False,
        }
