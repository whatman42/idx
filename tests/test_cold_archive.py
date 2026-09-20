"""Cold archive — GitHub Free backends, isolation, no GDrive."""
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
from src.python.archive.integrity import (
    assert_no_secrets,
    extract_tar_gz,
    make_tar_gz,
    scan_secret_bytes,
    sha256_bytes,
)
from src.python.archive.manager import ArchiveManager


def test_roundtrip_compress_hash_restore(tmp_path):
    m = ArchiveManager(local_root=tmp_path / "cold", prefer_github_release=False)
    files = {"a.json": b'{"x":1}', "b.csv": b"a,b\n1,2\n"}
    r = m.archive_files(files, artifact_id="art-1", artifact_type="research")
    assert r.ok
    assert r.backend == "local"
    assert r.reference is not None
    assert r.reference.compression == "tar.gz"

    r2 = m.archive_files(files, artifact_id="art-1", artifact_type="research")
    assert r2.ok and r2.idempotent
    assert r2.status == ArchiveStatus.ARCHIVE_ALREADY_PRESENT.value

    restored = m.restore(
        identity=r.reference.archive_identity,
        expected_archive_sha256=r.reference.archive_sha256,
        dest_dir=tmp_path / "restore",
    )
    assert restored.ok
    data = Path(restored.reference.local_path).read_bytes()
    assert sha256_bytes(data) == r.reference.archive_sha256
    assert extract_tar_gz(data)["a.json"] == files["a.json"]


def test_conflict_same_id_different_hash(tmp_path):
    m = ArchiveManager(local_root=tmp_path / "c", prefer_github_release=False)
    m.archive_files({"f.txt": b"v1"}, artifact_id="same")
    r = m.archive_files({"f.txt": b"v2-different"}, artifact_id="same")
    assert r.ok is False
    assert r.status == ArchiveStatus.ARCHIVE_CONFLICT.value


def test_secret_blocked(tmp_path):
    m = ArchiveManager(local_root=tmp_path / "s", prefer_github_release=False)
    r = m.archive_files(
        {"credentials.json": b'{"client_secret": "abcdefghijklmnop"}'},
        artifact_id="bad",
    )
    assert r.ok is False
    assert r.status == ArchiveStatus.ARCHIVE_BLOCKED_SECRET_DETECTED.value


def test_integrity_corruption(tmp_path):
    m = ArchiveManager(local_root=tmp_path / "i", prefer_github_release=False)
    r = m.archive_files({"x": b"ok"}, artifact_id="i1")
    assert r.ok
    Path(r.reference.local_path).write_bytes(b"corrupted-bytes")
    out = m.restore(
        identity=r.reference.archive_identity,
        expected_archive_sha256=r.reference.archive_sha256,
    )
    assert out.ok is False


def test_isolation_and_no_gdrive_import():
    assert archive_cannot_mutate_ledger() is True
    assert archive_cannot_mutate_champion() is True
    assert archive_cannot_approve_evidence() is True
    assert archive_cannot_affect_trading() is True
    with pytest.raises(ImportError):
        from src.python.archive.gdrive_backend import GoogleDriveBackend  # noqa: F401
    from src.python.ops import paper_portfolio  # noqa: F401


def test_deterministic_tar():
    a = make_tar_gz({"z": b"1", "a": b"2"})
    b = make_tar_gz({"a": b"2", "z": b"1"})
    assert sha256_bytes(a) == sha256_bytes(b)


def test_github_release_mock_idempotent(tmp_path):
    class FakeRelease:
        name = "github_release"
        def available(self):
            return True
        def put(self, **kw):
            if not hasattr(self, "_seen"):
                self._seen = set()
            if kw["asset_name"] in self._seen:
                return {**kw, "idempotent": True, "status": "ARCHIVE_ALREADY_PRESENT", "file_id": "1"}
            self._seen.add(kw["asset_name"])
            return {**kw, "idempotent": False, "status": "ARCHIVE_SUCCESS", "file_id": "1"}
        def get(self, **kw):
            return None

    m = ArchiveManager(
        local_root=tmp_path / "g", prefer_github_release=True, release_backend=FakeRelease()
    )
    files = {"m.json": b"{}"}
    r1 = m.archive_files(files, artifact_id="cert/1", artifact_type="certification")
    assert r1.ok and r1.backend == "github_release"
    r2 = m.archive_files(files, artifact_id="cert/1", artifact_type="certification")
    assert r2.idempotent


def test_scan_patterns():
    assert scan_secret_bytes(b"hello") == []
    with pytest.raises(ValueError):
        assert_no_secrets(b"ghp_abcdefghijklmnopqrstuvwxyz012345")
