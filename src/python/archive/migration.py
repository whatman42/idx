"""GitHub/local → Drive cold-archive migration (fail-closed, SHA-256, FIFO).

Maintenance plane only. Never mutates Ledger / Champion / trading.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.python.archive.drive_fs_backend import DriveFsBackend
from src.python.archive.integrity import scan_secret_bytes, sha256_bytes

MIGRATION_VERSION = "1.0.0"
SCHEMA_VERSION = "archive_mig_v1"


class MigrationStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    DOWNLOADED = "DOWNLOADED"
    HASH_VERIFIED = "HASH_VERIFIED"
    UPLOADED = "UPLOADED"
    TARGET_VERIFIED = "TARGET_VERIFIED"
    MANIFEST_VERIFIED = "MANIFEST_VERIFIED"
    MIGRATED = "MIGRATED"
    ROTATION_ELIGIBLE = "ROTATION_ELIGIBLE"
    ROTATION_STARTED = "ROTATION_STARTED"
    ROTATED = "ROTATED"
    FAILED = "FAILED"
    CONFLICT = "CONFLICT"
    BLOCKED = "BLOCKED"
    ARCHIVE_ALREADY_MIGRATED = "ARCHIVE_ALREADY_MIGRATED"
    ROTATION_BLOCKED = "ROTATION_BLOCKED"


@dataclass
class MigrationRecord:
    migration_id: str
    archive_id: str
    source: str
    source_sha256: str = ""
    target_sha256: str = ""
    size_bytes: int = 0
    started_at: str = ""
    completed_at: str = ""
    status: str = MigrationStatus.DISCOVERED.value
    error_code: str = ""
    source_commit: str = ""
    drive_path: str = ""
    cycle_date: str = ""
    filename: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in list(d.keys()):
            if any(s in k.lower() for s in ("token", "secret", "password", "credential", "api_key")):
                d.pop(k, None)
        return d


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cycle_date_from_name(name: str) -> str:
    m = re.search(r"(20\d{2}-\d{2}-\d{2})", name)
    if m:
        return m.group(1)
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@dataclass
class MigrationEngine:
    drive: DriveFsBackend
    journal_path: Path
    max_archives: int = 30
    min_recovery_archives: int = 3
    source_commit: str = ""

    def __post_init__(self) -> None:
        self.journal_path = Path(self.journal_path)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.journal_path.exists():
            self._save_journal([])

    def _load_journal(self) -> list[dict[str, Any]]:
        try:
            return json.loads(self.journal_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_journal(self, rows: list[dict[str, Any]]) -> None:
        clean = []
        for r in rows:
            text = json.dumps(r)
            if scan_secret_bytes(text.encode()):
                r = {k: v for k, v in r.items() if "token" not in k.lower()}
            clean.append(r)
        tmp = self.journal_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(clean, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.journal_path)

    def _append_journal(self, rec: MigrationRecord) -> None:
        rows = self._load_journal()
        rows.append(rec.to_dict())
        self._save_journal(rows)

    def inventory(self, source_archives: list[dict[str, Any]]) -> dict[str, Any]:
        migrated = self.drive.list_archives()
        mig_ids = {a.get("archive_id") for a in migrated}
        verified = [a for a in migrated if a.get("verified")]
        total = len(source_archives)
        done = sum(1 for s in source_archives if s.get("archive_id") in mig_ids)
        return {
            "total_source_archives": total,
            "migrated_archives": done,
            "verified_archives": len(verified),
            "failed_archives": sum(1 for r in self._load_journal() if r.get("status") == MigrationStatus.FAILED.value),
            "conflicted_archives": sum(1 for r in self._load_journal() if r.get("status") == MigrationStatus.CONFLICT.value),
            "missing_archives": max(0, total - done),
            "rotation_candidates": max(0, len(migrated) - self.max_archives),
            "recovery_copies": len(migrated),
        }

    def migrate_bytes(
        self,
        data: bytes,
        *,
        archive_id: str,
        filename: str = "",
        cycle_date: str = "",
        source: str = "github",
        extra_manifest: Optional[dict[str, Any]] = None,
    ) -> MigrationRecord:
        mid = f"mig-{uuid.uuid4().hex[:12]}"
        fname = filename or f"{archive_id}.tar.gz"
        cdate = cycle_date or _cycle_date_from_name(fname)
        rec = MigrationRecord(
            migration_id=mid,
            archive_id=archive_id,
            source=source,
            started_at=_utc_now(),
            source_commit=self.source_commit,
            cycle_date=cdate,
            filename=fname,
            status=MigrationStatus.DISCOVERED.value,
        )

        hits = scan_secret_bytes(data, name=fname)
        if hits:
            rec.status = MigrationStatus.FAILED.value
            rec.error_code = "SECRET_DETECTED"
            rec.completed_at = _utc_now()
            self._append_journal(rec)
            return rec

        source_sha = sha256_bytes(data)
        rec.source_sha256 = source_sha
        rec.size_bytes = len(data)
        rec.status = MigrationStatus.DOWNLOADED.value

        existing = self.drive.find_by_archive_id(archive_id)
        if existing:
            if existing.get("sha256") == source_sha:
                rec.status = MigrationStatus.ARCHIVE_ALREADY_MIGRATED.value
                rec.target_sha256 = source_sha
                rec.drive_path = str(existing.get("drive_path") or "")
                rec.completed_at = _utc_now()
                self._append_journal(rec)
                return rec
            rec.status = MigrationStatus.CONFLICT.value
            rec.error_code = "ARCHIVE_CONFLICT"
            rec.completed_at = _utc_now()
            self._append_journal(rec)
            return rec

        if not self.drive.available():
            rec.status = MigrationStatus.FAILED.value
            rec.error_code = "DRIVE_UNAVAILABLE"
            rec.completed_at = _utc_now()
            self._append_journal(rec)
            return rec

        rec.status = MigrationStatus.HASH_VERIFIED.value

        manifest = {
            "archive_id": archive_id,
            "cycle_id": cdate,
            "created_at": _utc_now(),
            "source": source,
            "source_commit": self.source_commit,
            "filename": fname,
            "size_bytes": len(data),
            "sha256": source_sha,
            "archive_format": "tar.gz",
            "schema_version": SCHEMA_VERSION,
            "migration_version": MIGRATION_VERSION,
            "verified": False,
            "verified_at": "",
            "retention_status": "ACTIVE",
        }
        if extra_manifest:
            for k, v in extra_manifest.items():
                if k not in manifest and not any(s in k.lower() for s in ("token", "secret", "password")):
                    manifest[k] = v

        try:
            row = self.drive.put(data, archive_id=archive_id, cycle_date=cdate, filename=fname, manifest=manifest)
        except Exception as e:
            rec.status = MigrationStatus.FAILED.value
            rec.error_code = f"UPLOAD_FAILED:{type(e).__name__}"
            rec.completed_at = _utc_now()
            self._append_journal(rec)
            return rec

        rec.status = MigrationStatus.UPLOADED.value
        rec.drive_path = str(row.get("drive_path") or "")

        try:
            target = self.drive.get_bytes(rec.drive_path)
        except Exception as e:
            rec.status = MigrationStatus.FAILED.value
            rec.error_code = f"TARGET_READ_FAILED:{type(e).__name__}"
            rec.completed_at = _utc_now()
            self._append_journal(rec)
            return rec

        target_sha = sha256_bytes(target)
        rec.target_sha256 = target_sha
        if target_sha != source_sha or len(target) != len(data):
            rec.status = MigrationStatus.FAILED.value
            rec.error_code = "HASH_OR_SIZE_MISMATCH"
            rec.completed_at = _utc_now()
            self._append_journal(rec)
            return rec

        rec.status = MigrationStatus.TARGET_VERIFIED.value
        manifest["verified"] = True
        manifest["verified_at"] = _utc_now()
        manifest["drive_path"] = rec.drive_path
        try:
            self.drive.put(data, archive_id=archive_id, cycle_date=cdate, filename=fname, manifest=manifest)
        except Exception:
            pass

        rec.status = MigrationStatus.MIGRATED.value
        rec.completed_at = _utc_now()
        self._append_journal(rec)
        return rec

    def fifo_rotate(self) -> dict[str, Any]:
        archives = [a for a in self.drive.list_archives() if a.get("verified")]

        def key(a: dict[str, Any]) -> tuple:
            return (str(a.get("created_at") or ""), str(a.get("cycle_id") or ""), str(a.get("archive_id") or ""))

        archives_sorted = sorted(archives, key=key)
        n = len(archives_sorted)
        if n <= self.max_archives:
            return {"status": "NO_ROTATION_NEEDED", "count": n, "deleted": []}
        to_delete_count = n - self.max_archives
        retain = max(self.min_recovery_archives, self.max_archives)
        if n - to_delete_count < self.min_recovery_archives:
            return {
                "status": MigrationStatus.ROTATION_BLOCKED.value,
                "count": n,
                "deleted": [],
                "reason": "MIN_RECOVERY_ARCHIVES",
            }
        deletable = archives_sorted[: max(0, n - retain)]
        deleted = []
        for a in deletable[:to_delete_count]:
            aid = str(a.get("archive_id") or "")
            if not aid:
                continue
            if self.drive.delete(aid):
                deleted.append(aid)
        return {
            "status": MigrationStatus.ROTATED.value if deleted else "NO_DELETE",
            "count": n,
            "deleted": deleted,
            "remaining": len(self.drive.list_archives()),
        }

    def restore_verify(self, archive_id: str) -> dict[str, Any]:
        row = self.drive.find_by_archive_id(archive_id)
        if not row:
            return {"ok": False, "error": "NOT_FOUND"}
        path = str(row.get("drive_path") or "")
        expected = str(row.get("sha256") or "")
        try:
            data = self.drive.get_bytes(path)
        except Exception as e:
            return {"ok": False, "error": f"READ:{type(e).__name__}"}
        got = sha256_bytes(data)
        if got != expected:
            return {"ok": False, "error": "HASH_MISMATCH", "expected": expected, "got": got}
        if len(data) != int(row.get("size_bytes") or len(data)):
            return {"ok": False, "error": "SIZE_MISMATCH"}
        return {"ok": True, "sha256": got, "size_bytes": len(data), "drive_path": path}


def discover_local_sources(root: Path) -> list[dict[str, Any]]:
    root = Path(root)
    out = []
    if not root.exists():
        return out
    for p in sorted(root.rglob("*.tar.gz")):
        data = p.read_bytes()
        out.append(
            {
                "archive_id": p.stem,
                "path": str(p),
                "filename": p.name,
                "size_bytes": len(data),
                "sha256": sha256_bytes(data),
                "source": "local_staging",
            }
        )
    return out
