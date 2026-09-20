"""Cold archive contracts — GitHub Free only (Releases + Actions Artifacts + local).

Never financial truth. Never promotion authority. Never trading dependency.
GDrive / R2 / S3 / paid object storage = FORBIDDEN.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ArchiveStatus(str, Enum):
    ARCHIVE_SUCCESS = "ARCHIVE_SUCCESS"
    ARCHIVE_ALREADY_PRESENT = "ARCHIVE_ALREADY_PRESENT"
    ARCHIVE_CONFLICT = "ARCHIVE_CONFLICT"
    ARCHIVE_INTEGRITY_FAILURE = "ARCHIVE_INTEGRITY_FAILURE"
    ARCHIVE_BLOCKED_SECRET_DETECTED = "ARCHIVE_BLOCKED_SECRET_DETECTED"
    ARCHIVE_SIZE_LIMIT_REACHED = "ARCHIVE_SIZE_LIMIT_REACHED"
    ARCHIVE_AUTH_FAILED = "ARCHIVE_AUTH_FAILED"
    ARCHIVE_PERMISSION_DENIED = "ARCHIVE_PERMISSION_DENIED"
    ARCHIVE_UNAVAILABLE = "ARCHIVE_UNAVAILABLE"
    ARCHIVE_DEGRADED = "ARCHIVE_DEGRADED"
    ARCHIVE_FAILED = "ARCHIVE_FAILED"
    ARCHIVE_INVALID = "ARCHIVE_INVALID"
    RESTORE_SUCCESS = "RESTORE_SUCCESS"
    RESTORE_INTEGRITY_FAILURE = "RESTORE_INTEGRITY_FAILURE"
    RESTORE_UNAVAILABLE = "RESTORE_UNAVAILABLE"


class ArtifactType(str, Enum):
    RESEARCH = "research"
    EVIDENCE = "evidence"
    EXPERIMENT = "experiment"
    REPORT = "reports"
    LOG = "logs"
    MODEL = "models"
    DATASET = "datasets"
    BACKUP = "backups"
    CERTIFICATION = "certification"
    AUDIT = "audit"


class RetentionClass(str, Enum):
    ACTIONS_7D = "actions_7d"
    ACTIONS_14D = "actions_14d"
    RELEASE_RETAIN = "release_retain"


SCHEMA_VERSION = 1
MAX_ARCHIVE_BYTES = 80 * 1024 * 1024


@dataclass(frozen=True)
class ArchiveReference:
    artifact_id: str
    artifact_type: str
    content_sha256: str
    archive_sha256: str
    size_bytes: int
    compressed_bytes: int
    schema_version: int
    created_at: str
    source: str
    backend: str
    archive_identity: str
    compression: str = "tar.gz"
    retention_class: str = RetentionClass.RELEASE_RETAIN.value
    integrity_status: str = "OK"
    release_tag: str = ""
    asset_name: str = ""
    local_path: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        prov = {
            k: v
            for k, v in (self.provenance or {}).items()
            if not any(s in k.lower() for s in ("token", "secret", "password", "credential", "api_key"))
        }
        d["provenance"] = prov
        return d


@dataclass
class ArchiveResult:
    status: str
    ok: bool
    reference: Optional[ArchiveReference] = None
    message: str = ""
    error_type: str = ""
    backend: str = "none"
    idempotent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.ok,
            "reference": self.reference.to_dict() if self.reference else None,
            "message": self.message,
            "error_type": self.error_type,
            "backend": self.backend,
            "idempotent": self.idempotent,
        }


def archive_identity(artifact_id: str, content_sha256: str, schema_version: int = SCHEMA_VERSION) -> str:
    return f"{artifact_id}:{content_sha256}:{schema_version}"


def archive_cannot_mutate_ledger() -> bool:
    return True


def archive_cannot_mutate_champion() -> bool:
    return True


def archive_cannot_approve_evidence() -> bool:
    return True


def archive_cannot_affect_trading() -> bool:
    return True
