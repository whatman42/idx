"""Cold archive — integrity, idempotency, isolation, GDrive-unavailable != trading fail."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.python.archive.contracts import (
    ArchiveStatus,
    archive_cannot_affect_trading,
    archive_cannot_approve_evidence,
    archive_cannot_mutate_champion,
    archive_cannot_mutate_ledger,
)
from src.python.archive.integrity import assert_no_secrets, scan_secret_bytes, sha256_bytes
from src.python.archive.manager import ArchiveManager


def test_local_roundtrip(tmp_path):
    m = ArchiveManager(local_root=tmp_path / "cold", prefer_gdrive=False)
    data = b"deterministic-payload-001"
    r = m.archive_bytes(data, artifact_id="art-1", artifact_type="research", source="test")
    assert r.ok
    assert r.local_persisted is True
    assert r.remote_persisted is False
    assert r.backend == "local"
    assert r.reference is not None
    assert r.reference.content_hash == sha256_bytes(data)

    r2 = m.archive_bytes(data, artifact_id="art-1", artifact_type="research")
    assert r2.idempotent is True

    restored = m.restore(
        file_id=r.reference.drive_file_id,
        expected_hash=r.reference.content_hash,
        dest_dir=tmp_path / "restore",
    )
    assert restored.ok
    assert restored.status == ArchiveStatus.RESTORE_SUCCESS.value
    assert Path(restored.reference.local_path).read_bytes() == data


def test_secret_rejected(tmp_path):
    m = ArchiveManager(local_root=tmp_path / "c", prefer_gdrive=False)
    bad = b'{"client_secret": "supersecretvalue123456"}'
    r = m.archive_bytes(bad, artifact_id="x", name="credentials.json")
    assert r.ok is False
    assert r.status == ArchiveStatus.ARCHIVE_REJECTED_SECRET.value


def test_isolation_flags():
    assert archive_cannot_mutate_ledger() is True
    assert archive_cannot_mutate_champion() is True
    assert archive_cannot_approve_evidence() is True
    assert archive_cannot_affect_trading() is True


def test_gdrive_unavailable_paper_still_ok(tmp_path):
    class DeadDrive:
        name = "gdrive"
        def available(self):
            return False
        def put(self, **kwargs):
            raise RuntimeError("AUTH_FAILED")
        def get(self, **kwargs):
            raise RuntimeError("AUTH_FAILED")

    m = ArchiveManager(local_root=tmp_path / "c2", prefer_gdrive=True, gdrive_backend=DeadDrive())
    r = m.archive_bytes(b"payload", artifact_id="p1", artifact_type="reports")
    assert r.ok is True
    assert r.local_persisted is True
    assert r.remote_persisted is False

    from src.python.ops import paper_portfolio  # noqa: F401
    assert archive_cannot_affect_trading() is True


def test_integrity_mismatch_on_restore(tmp_path):
    m = ArchiveManager(local_root=tmp_path / "c3", prefer_gdrive=False)
    r = m.archive_bytes(b"abc", artifact_id="i1")
    assert r.ok
    Path(r.reference.local_path).write_bytes(b"corrupted")
    out = m.restore(file_id=r.reference.drive_file_id, expected_hash=r.reference.content_hash)
    assert out.ok is False
    assert out.status in (
        ArchiveStatus.RESTORE_INTEGRITY_FAILURE.value,
        ArchiveStatus.RESTORE_UNAVAILABLE.value,
    )


def test_scan_patterns():
    assert scan_secret_bytes(b"hello") == []
    assert scan_secret_bytes(b"Bearer abcdefghijklmnopqrstuvwxyz0123456789") != []
    with pytest.raises(ValueError):
        assert_no_secrets(b"-----BEGIN RSA PRIVATE KEY-----\nxxx")


def test_mock_gdrive_success(tmp_path):
    class FakeDrive:
        name = "gdrive"
        def available(self):
            return True
        def put(self, **kw):
            return {
                "logical_id": kw["logical_id"],
                "content_hash": kw["content_hash"],
                "size_bytes": len(kw["data"]),
                "file_id": "drive-file-1",
                "folder_id": "drive-folder-1",
                "folder_key": kw["folder_key"],
                "meta": kw["meta"],
                "idempotent": False,
            }
        def get(self, **kw):
            return None

    m = ArchiveManager(local_root=tmp_path / "c4", prefer_gdrive=True, gdrive_backend=FakeDrive())
    r = m.archive_bytes(b"cloud-ish", artifact_id="g1", artifact_type="certification")
    assert r.ok
    assert r.remote_persisted is True
    assert r.backend == "gdrive"
    assert r.reference.drive_file_id == "drive-file-1"
