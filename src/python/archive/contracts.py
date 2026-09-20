"""Cold archive domain contracts — GDrive is COLD_ARCHIVE_STORAGE only.

Never financial truth. Never promotion authority. Never trading dependency.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ArchiveStatus(str, Enum):
    ARCHIVE_SUCCESS = "ARCHIVE_SUCCESS"
    ARCHIVE_UNAVAILABLE = "ARCHIVE_UNAVAILABLE"
    ARCHIVE_AUTH_FAILED = "ARCHIVE_AUTH_FAILED"
    ARCHIVE_PERMISSION_DENIED = "ARCHIVE_PERMISSION_DENIED"
    ARCHIVE_RATE_LIMITED = "ARCHIVE_RATE_LIMITED"
    ARCHIVE_INTEGRITY_FAILURE = "ARCHIVE_INTEGRITY_FAILURE"
    ARCHIVE_NOT_FOUND = "ARCHIVE_NOT_FOUND"
    ARCHIVE_REJECTED_SECRET = "ARCHIVE_REJECTED_SECRET"
    ARCHIVE_INVALID = "ARCHIVE_INVALID"
    ARCHIVE_IDEMPOTENT = "ARCHIVE_IDEMPOTENT"
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
    COLD = "COLD"
    ARCHIVE = "ARCHIVE"


SCHEMA_VERSION = 1
DRIVE_ROOT_FOLDER_NAME = "IDX"
DRIVE_COLD_FOLDER_NAME = "cold"


@dataclass(frozen=True)
class ArchiveReference:
    artifact_id: str
    artifact_type: str
    content_hash: str
    size_bytes: int
    schema_version: int
    created_at: str
    archived_at: str
    source: str
    backend: str
    drive_file_id: str = ""
    drive_folder_id: str = ""
    retention_class: str = RetentionClass.COLD.value
    compression: str = "none"
    encryption_status: str = "none"
    integrity_status: str = "OK"
    provenance: dict[str, Any] = field(default_factory=dict)
    local_path: str = ""

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
    remote_persisted: bool = False
    local_persisted: bool = False
    backend: str = "none"
    idempotent: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "ok": self.ok,
            "reference": self.reference.to_dict() if self.reference else None,
            "message": self.message,
            "error_type": self.error_type,
            "remote_persisted": self.remote_persisted,
            "local_persisted": self.local_persisted,
            "backend": self.backend,
            "idempotent": self.idempotent,
        }


def archive_cannot_mutate_ledger() -> bool:
    return True


def archive_cannot_mutate_champion() -> bool:
    return True


def archive_cannot_approve_evidence() -> bool:
    return True


def archive_cannot_affect_trading() -> bool:
    return True
