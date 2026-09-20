"""ArchiveManager — compress → hash → secret-scan → persist (local / GitHub Release).

Archive failure must NOT block paper trading.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from src.python.archive.contracts import (
    MAX_ARCHIVE_BYTES,
    SCHEMA_VERSION,
    ArchiveReference,
    ArchiveResult,
    ArchiveStatus,
    ArtifactType,
    RetentionClass,
    archive_identity,
)
from src.python.archive.integrity import assert_no_secrets, make_tar_gz, sha256_bytes
from src.python.archive.local_backend import LocalArchiveBackend


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ArchiveManager:
    def __init__(
        self,
        *,
        local_root: Optional[str | Path] = None,
        prefer_github_release: bool = False,
        release_backend: Any = None,
    ) -> None:
        root = local_root or os.environ.get("IDX_ARCHIVE_LOCAL_ROOT", "/tmp/idx_cold_archive")
        self.local = LocalArchiveBackend(root)
        self.release = release_backend
        self.prefer_github_release = prefer_github_release
        if prefer_github_release and release_backend is None:
            try:
                from src.python.archive.github_release_backend import GitHubReleaseArchiveBackend
                self.release = GitHubReleaseArchiveBackend()
            except Exception:
                self.release = None

    def archive_files(
        self,
        files: Mapping[str, bytes],
        *,
        artifact_id: str,
        artifact_type: str = ArtifactType.RESEARCH.value,
        source: str = "idx",
        release_tag: str = "",
        provenance: Optional[dict[str, Any]] = None,
        retention: str = RetentionClass.RELEASE_RETAIN.value,
    ) -> ArchiveResult:
        if not artifact_id or not files:
            return ArchiveResult(
                status=ArchiveStatus.ARCHIVE_INVALID.value, ok=False, message="missing_input"
            )
        try:
            for n, blob in files.items():
                assert_no_secrets(blob, name=n)
        except ValueError as e:
            return ArchiveResult(
                status=ArchiveStatus.ARCHIVE_BLOCKED_SECRET_DETECTED.value,
                ok=False,
                message=str(e)[:120],
            )
        content_blob = b"\n".join(
            f"{k}:{sha256_bytes(v)}".encode() for k, v in sorted(files.items())
        )
        content_sha = sha256_bytes(content_blob)
        try:
            archive_bytes = make_tar_gz(files)
        except ValueError as e:
            return ArchiveResult(
                status=ArchiveStatus.ARCHIVE_BLOCKED_SECRET_DETECTED.value,
                ok=False,
                message=str(e)[:120],
            )
        if len(archive_bytes) > MAX_ARCHIVE_BYTES:
            return ArchiveResult(
                status=ArchiveStatus.ARCHIVE_SIZE_LIMIT_REACHED.value,
                ok=False,
                message=f"size={len(archive_bytes)}",
            )
        archive_sha = sha256_bytes(archive_bytes)
        identity = archive_identity(artifact_id, content_sha)
        meta = {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "content_sha256": content_sha,
            "archive_sha256": archive_sha,
            "archive_identity": identity,
            "compression": "tar.gz",
            "file_count": len(files),
            "uncompressed_bytes": sum(len(v) for v in files.values()),
            "compressed_bytes": len(archive_bytes),
            "source": source,
            "retention_class": retention,
            "provenance": provenance or {},
        }
        asset_name = f"{artifact_id.replace('/', '_')}_{content_sha[:12]}.tar.gz"
        tag = release_tag or f"idx-archive-{artifact_type}-{content_sha[:8]}"

        backend = self.local
        backend_name = "local"
        if self.prefer_github_release and self.release is not None:
            try:
                if self.release.available():
                    backend = self.release
                    backend_name = "github_release"
            except Exception:
                pass

        try:
            if backend_name == "github_release":
                rec = backend.put(
                    identity=identity,
                    artifact_id=artifact_id,
                    content_sha256=content_sha,
                    archive_bytes=archive_bytes,
                    archive_sha256=archive_sha,
                    meta=meta,
                    folder_key=artifact_type,
                    release_tag=tag,
                    asset_name=asset_name,
                )
            else:
                rec = backend.put(
                    identity=identity,
                    artifact_id=artifact_id,
                    content_sha256=content_sha,
                    archive_bytes=archive_bytes,
                    archive_sha256=archive_sha,
                    meta=meta,
                    folder_key=artifact_type,
                )
        except Exception as e:
            err = str(e)
            if backend_name == "github_release":
                try:
                    rec = self.local.put(
                        identity=identity,
                        artifact_id=artifact_id,
                        content_sha256=content_sha,
                        archive_bytes=archive_bytes,
                        archive_sha256=archive_sha,
                        meta=meta,
                        folder_key=artifact_type,
                    )
                    backend_name = "local"
                except Exception as e2:
                    st = ArchiveStatus.ARCHIVE_UNAVAILABLE.value
                    if "AUTH" in err:
                        st = ArchiveStatus.ARCHIVE_AUTH_FAILED.value
                    return ArchiveResult(
                        status=st, ok=False, message=err[:120], error_type=type(e2).__name__
                    )
            else:
                return ArchiveResult(
                    status=ArchiveStatus.ARCHIVE_FAILED.value,
                    ok=False,
                    message=err[:120],
                    error_type=type(e).__name__,
                )

        status = rec.get("status") or ArchiveStatus.ARCHIVE_SUCCESS.value
        if status == "ARCHIVE_CONFLICT":
            return ArchiveResult(
                status=ArchiveStatus.ARCHIVE_CONFLICT.value,
                ok=False,
                message=str(rec.get("existing_identity") or rec.get("existing_asset") or "conflict"),
                backend=backend_name,
            )
        idempotent = bool(rec.get("idempotent")) or status == "ARCHIVE_ALREADY_PRESENT"
        if idempotent:
            status = ArchiveStatus.ARCHIVE_ALREADY_PRESENT.value
        elif status != ArchiveStatus.ARCHIVE_SUCCESS.value:
            status = ArchiveStatus.ARCHIVE_SUCCESS.value

        ref = ArchiveReference(
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            content_sha256=content_sha,
            archive_sha256=archive_sha,
            size_bytes=sum(len(v) for v in files.values()),
            compressed_bytes=len(archive_bytes),
            schema_version=SCHEMA_VERSION,
            created_at=_now(),
            source=source,
            backend=backend_name,
            archive_identity=identity,
            compression="tar.gz",
            retention_class=retention,
            release_tag=str(rec.get("release_tag") or (tag if backend_name == "github_release" else "")),
            asset_name=str(rec.get("asset_name") or (asset_name if backend_name == "github_release" else "")),
            local_path=str(rec.get("path") or ""),
            provenance=provenance or {},
        )
        return ArchiveResult(
            status=status,
            ok=True,
            reference=ref,
            backend=backend_name,
            idempotent=idempotent,
        )

    def archive_bytes(
        self,
        data: bytes,
        *,
        artifact_id: str,
        artifact_type: str = ArtifactType.RESEARCH.value,
        source: str = "idx",
        name: str = "payload.bin",
        **kwargs: Any,
    ) -> ArchiveResult:
        return self.archive_files(
            {name: data},
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            source=source,
            **kwargs,
        )

    def restore(
        self,
        *,
        file_id: str = "",
        identity: str = "",
        expected_archive_sha256: str = "",
        dest_dir: Optional[str | Path] = None,
        download_url: str = "",
    ) -> ArchiveResult:
        backends = []
        if self.release is not None:
            backends.append(self.release)
        backends.append(self.local)
        last_err = ""
        for b in backends:
            try:
                if getattr(b, "name", "") == "github_release":
                    got = b.get(file_id=file_id, identity=identity, download_url=download_url)
                else:
                    got = b.get(file_id=file_id, identity=identity)
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
            exp = expected_archive_sha256 or rec.get("archive_sha256") or ""
            if exp and h != exp:
                return ArchiveResult(
                    status=ArchiveStatus.RESTORE_INTEGRITY_FAILURE.value,
                    ok=False,
                    message="expected_hash_mismatch",
                    backend=getattr(b, "name", "unknown"),
                )
            out_dir = Path(dest_dir or "/tmp/idx_archive_restore")
            out_dir.mkdir(parents=True, exist_ok=True)
            tmp = out_dir / f".tmp_{h[:16]}.tar.gz"
            final = out_dir / f"{h[:16]}.tar.gz"
            tmp.write_bytes(data)
            tmp.replace(final)
            ref = ArchiveReference(
                artifact_id=str(rec.get("artifact_id") or identity or ""),
                artifact_type="research",
                content_sha256=str(rec.get("content_sha256") or ""),
                archive_sha256=h,
                size_bytes=len(data),
                compressed_bytes=len(data),
                schema_version=SCHEMA_VERSION,
                created_at=_now(),
                source="restore",
                backend=getattr(b, "name", "unknown"),
                archive_identity=str(rec.get("identity") or identity),
                local_path=str(final),
            )
            return ArchiveResult(
                status=ArchiveStatus.RESTORE_SUCCESS.value,
                ok=True,
                reference=ref,
                backend=getattr(b, "name", "unknown"),
            )
        return ArchiveResult(
            status=ArchiveStatus.RESTORE_UNAVAILABLE.value,
            ok=False,
            message=last_err or "not_found",
            backend="none",
        )


def get_archive_manager(**kwargs: Any) -> ArchiveManager:
    return ArchiveManager(**kwargs)
