"""ArchiveManager — prepare → validate → hash → upload → verify → reference.

GDrive unavailable must NOT block paper trading.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.python.archive.contracts import (
    SCHEMA_VERSION,
    ArchiveReference,
    ArchiveResult,
    ArchiveStatus,
    ArtifactType,
    RetentionClass,
)
from src.python.archive.integrity import assert_no_secrets, sha256_bytes
from src.python.archive.local_backend import LocalArchiveBackend


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _logical_id(artifact_id: str, content_hash: str, schema_version: int = SCHEMA_VERSION) -> str:
    return f"{artifact_id}|{content_hash}|v{schema_version}"


class ArchiveManager:
    def __init__(
        self,
        *,
        local_root: Optional[str | Path] = None,
        prefer_gdrive: bool = True,
        gdrive_backend: Any = None,
    ) -> None:
        root = local_root or os.environ.get("IDX_ARCHIVE_LOCAL_ROOT", "/tmp/idx_cold_archive")
        self.local = LocalArchiveBackend(root)
        self.gdrive = gdrive_backend
        self.prefer_gdrive = prefer_gdrive
        if prefer_gdrive and gdrive_backend is None:
            try:
                from src.python.archive.gdrive_backend import GoogleDriveBackend
                self.gdrive = GoogleDriveBackend.from_env()
            except Exception:
                self.gdrive = None

    def _backend_for_write(self) -> tuple[Any, str]:
        if self.prefer_gdrive and self.gdrive is not None:
            try:
                if self.gdrive.available():
                    return self.gdrive, "gdrive"
            except Exception:
                pass
        return self.local, "local"

    def archive_bytes(
        self,
        data: bytes,
        *,
        artifact_id: str,
        artifact_type: str = ArtifactType.RESEARCH.value,
        source: str = "idx",
        provenance: Optional[dict[str, Any]] = None,
        retention: str = RetentionClass.COLD.value,
        name: str = "",
    ) -> ArchiveResult:
        if not artifact_id:
            return ArchiveResult(
                status=ArchiveStatus.ARCHIVE_INVALID.value,
                ok=False,
                message="missing_artifact_id",
            )
        try:
            assert_no_secrets(data, name=name or artifact_id)
        except ValueError as e:
            return ArchiveResult(
                status=ArchiveStatus.ARCHIVE_REJECTED_SECRET.value,
                ok=False,
                message=str(e)[:120],
            )
        content_hash = sha256_bytes(data)
        logical = _logical_id(artifact_id, content_hash)
        meta = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "schema_version": SCHEMA_VERSION,
            "source": source,
            "provenance": provenance or {},
            "retention_class": retention,
        }
        backend, backend_name = self._backend_for_write()
        try:
            rec = backend.put(
                logical_id=logical,
                data=data,
                content_hash=content_hash,
                meta=meta,
                folder_key=artifact_type,
            )
        except Exception as e:
            err = str(e)
            status = ArchiveStatus.ARCHIVE_UNAVAILABLE.value
            if "AUTH" in err:
                status = ArchiveStatus.ARCHIVE_AUTH_FAILED.value
            elif "PERMISSION" in err:
                status = ArchiveStatus.ARCHIVE_PERMISSION_DENIED.value
            elif "429" in err or "RATE" in err:
                status = ArchiveStatus.ARCHIVE_RATE_LIMITED.value
            if backend_name == "gdrive":
                try:
                    rec = self.local.put(
                        logical_id=logical,
                        data=data,
                        content_hash=content_hash,
                        meta=meta,
                        folder_key=artifact_type,
                    )
                    backend_name = "local"
                except Exception as e2:
                    return ArchiveResult(
                        status=status,
                        ok=False,
                        message=err[:120],
                        error_type=type(e2).__name__,
                        backend="none",
                    )
            else:
                return ArchiveResult(
                    status=status,
                    ok=False,
                    message=err[:120],
                    error_type=type(e).__name__,
                    backend="none",
                )

        ref = ArchiveReference(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            content_hash=content_hash,
            size_bytes=len(data),
            schema_version=SCHEMA_VERSION,
            created_at=_now(),
            archived_at=_now(),
            source=source,
            backend=backend_name,
            drive_file_id=str(rec.get("file_id") or ""),
            drive_folder_id=str(rec.get("folder_id") or ""),
            retention_class=retention,
            provenance=provenance or {},
            local_path=str(rec.get("path") or ""),
            integrity_status="OK",
        )
        idempotent = bool(rec.get("idempotent"))
        return ArchiveResult(
            status=(
                ArchiveStatus.ARCHIVE_IDEMPOTENT.value
                if idempotent
                else ArchiveStatus.ARCHIVE_SUCCESS.value
            ),
            ok=True,
            reference=ref,
            remote_persisted=(backend_name == "gdrive"),
            local_persisted=(backend_name == "local"),
            backend=backend_name,
            idempotent=idempotent,
        )

    def restore(
        self,
        *,
        file_id: str = "",
        logical_id: str = "",
        expected_hash: str = "",
        dest_dir: Optional[str | Path] = None,
    ) -> ArchiveResult:
        backends = []
        if self.gdrive is not None:
            backends.append(self.gdrive)
        backends.append(self.local)
        last_err = ""
        for b in backends:
            try:
                got = b.get(file_id=file_id, logical_id=logical_id)
            except ValueError as e:
                if "INTEGRITY" in str(e):
                    return ArchiveResult(
                        status=ArchiveStatus.RESTORE_INTEGRITY_FAILURE.value,
                        ok=False,
                        message="hash_mismatch",
                        backend=getattr(b, "name", "unknown"),
                    )
                last_err = str(e)
                continue
            except Exception as e:
                last_err = str(e)[:120]
                continue
            if got is None:
                continue
            data, rec = got
            h = sha256_bytes(data)
            if expected_hash and h != expected_hash:
                return ArchiveResult(
                    status=ArchiveStatus.RESTORE_INTEGRITY_FAILURE.value,
                    ok=False,
                    message="expected_hash_mismatch",
                    backend=getattr(b, "name", "unknown"),
                )
            out_dir = Path(dest_dir or "/tmp/idx_archive_restore")
            out_dir.mkdir(parents=True, exist_ok=True)
            tmp = out_dir / f".tmp_{h[:16]}"
            final = out_dir / f"{h[:16]}.restored"
            tmp.write_bytes(data)
            tmp.replace(final)
            ref = ArchiveReference(
                artifact_id=str(rec.get("logical_id") or logical_id or ""),
                artifact_type=str((rec.get("meta") or {}).get("artifact_type") or "research"),
                content_hash=h,
                size_bytes=len(data),
                schema_version=SCHEMA_VERSION,
                created_at=_now(),
                archived_at=_now(),
                source="restore",
                backend=getattr(b, "name", "unknown"),
                drive_file_id=str(rec.get("file_id") or file_id),
                local_path=str(final),
                integrity_status="OK",
            )
            return ArchiveResult(
                status=ArchiveStatus.RESTORE_SUCCESS.value,
                ok=True,
                reference=ref,
                remote_persisted=getattr(b, "name", "") == "gdrive",
                local_persisted=getattr(b, "name", "") == "local",
                backend=getattr(b, "name", "unknown"),
            )
        if "AUTH" in last_err:
            st = ArchiveStatus.ARCHIVE_AUTH_FAILED.value
        elif "NOT_FOUND" in last_err:
            st = ArchiveStatus.ARCHIVE_NOT_FOUND.value
        else:
            st = ArchiveStatus.RESTORE_UNAVAILABLE.value
        return ArchiveResult(status=st, ok=False, message=last_err or "not_found", backend="none")


def get_archive_manager(**kwargs: Any) -> ArchiveManager:
    return ArchiveManager(**kwargs)
