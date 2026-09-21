"""Cold archive migration: GitHub/local → Drive FS bridge (SHA-256, FIFO, fail-closed)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.python.archive.drive_fs_backend import DriveFsBackend
from src.python.archive.integrity import make_tar_gz, sha256_bytes
from src.python.archive.migration import MigrationEngine, MigrationStatus, discover_local_sources
from src.python.archive.contracts import archive_cannot_affect_trading
from src.python.ops.paper_portfolio import new_session, apply_long_entry


def _blob(name: str = "a.json", body: bytes = b'{"ok":1}') -> bytes:
    return make_tar_gz({name: body})


def test_sha256_source_target_match(tmp_path):
    drive = DriveFsBackend(tmp_path / "drive")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "journal.json")
    data = _blob()
    rec = eng.migrate_bytes(data, archive_id="art-1", filename="art-1.tar.gz", cycle_date="2026-09-21")
    assert rec.status == MigrationStatus.MIGRATED.value
    assert rec.source_sha256 == rec.target_sha256
    assert rec.source_sha256 == sha256_bytes(data)


def test_sha256_mismatch_blocks_migration(tmp_path):
    drive = DriveFsBackend(tmp_path / "drive")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "j.json")
    data = _blob()
    orig_put = drive.put

    def bad_put(data_b, **kw):
        row = orig_put(data_b, **kw)
        Path(row["local_abs"]).write_bytes(b"CORRUPT")
        return row

    drive.put = bad_put  # type: ignore
    rec = eng.migrate_bytes(data, archive_id="bad-hash", filename="x.tar.gz", cycle_date="2026-09-21")
    assert rec.status == MigrationStatus.FAILED.value
    assert "HASH" in rec.error_code or "MISMATCH" in rec.error_code


def test_duplicate_archive_is_idempotent(tmp_path):
    drive = DriveFsBackend(tmp_path / "d")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "j.json")
    data = _blob()
    r1 = eng.migrate_bytes(data, archive_id="same", filename="same.tar.gz", cycle_date="2026-09-21")
    r2 = eng.migrate_bytes(data, archive_id="same", filename="same.tar.gz", cycle_date="2026-09-21")
    assert r1.status == MigrationStatus.MIGRATED.value
    assert r2.status == MigrationStatus.ARCHIVE_ALREADY_MIGRATED.value


def test_archive_hash_conflict(tmp_path):
    drive = DriveFsBackend(tmp_path / "d")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "j.json")
    eng.migrate_bytes(_blob("a", b"v1"), archive_id="c1", filename="c1.tar.gz", cycle_date="2026-09-21")
    r = eng.migrate_bytes(_blob("a", b"v2"), archive_id="c1", filename="c1.tar.gz", cycle_date="2026-09-21")
    assert r.status == MigrationStatus.CONFLICT.value


def test_drive_unavailable_preserves_source(tmp_path):
    drive = DriveFsBackend(tmp_path / "d")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "j.json")
    drive.available = lambda: False  # type: ignore
    rec = eng.migrate_bytes(_blob(), archive_id="u1", filename="u1.tar.gz", cycle_date="2026-09-21")
    assert rec.status == MigrationStatus.FAILED.value
    assert rec.error_code == "DRIVE_UNAVAILABLE"


def test_fifo_oldest_first_and_recovery_protect(tmp_path):
    drive = DriveFsBackend(tmp_path / "d")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "j.json", max_archives=3, min_recovery_archives=2)
    for i in range(5):
        day = f"2026-09-{10+i:02d}"
        eng.migrate_bytes(_blob("f", f"v{i}".encode()), archive_id=f"a{i}", filename=f"a{i}.tar.gz", cycle_date=day)
    result = eng.fifo_rotate()
    assert result["status"] == MigrationStatus.ROTATED.value
    remaining = drive.list_archives()
    assert len(remaining) >= eng.min_recovery_archives
    ids = {a["archive_id"] for a in remaining}
    assert "a4" in ids


def test_restore_valid_and_corrupt(tmp_path):
    drive = DriveFsBackend(tmp_path / "d")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "j.json")
    data = _blob()
    rec = eng.migrate_bytes(data, archive_id="rv1", filename="rv1.tar.gz", cycle_date="2026-09-21")
    assert rec.status == MigrationStatus.MIGRATED.value
    assert eng.restore_verify("rv1")["ok"] is True
    Path(drive.root / rec.drive_path).write_bytes(b"xxx")
    assert eng.restore_verify("rv1")["ok"] is False


def test_core_does_not_depend_on_drive_and_survives_failure(tmp_path):
    assert archive_cannot_affect_trading() is True
    state = new_session(initial_capital=5_000_000.0)
    state, trade, status = apply_long_entry(
        state, symbol="AAA", price=100.0, weight=0.05,
        signal_id="mig_iso", timestamp="2026-09-21T02:00:00+00:00",
    )
    assert status == "FULL_FILL"
    drive = DriveFsBackend(tmp_path / "d")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "j.json")
    drive.available = lambda: False  # type: ignore
    eng.migrate_bytes(_blob(), archive_id="x", filename="x.tar.gz", cycle_date="2026-09-21")
    assert state.cash < 5_000_000.0


def test_migration_journal_no_secrets(tmp_path):
    drive = DriveFsBackend(tmp_path / "d")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "j.json")
    eng.migrate_bytes(_blob(), archive_id="js1", filename="js1.tar.gz", cycle_date="2026-09-21")
    text = Path(tmp_path / "j.json").read_text()
    assert "TELEGRAM_BOT_TOKEN=" not in text


def test_migration_inventory(tmp_path):
    drive = DriveFsBackend(tmp_path / "d")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "j.json")
    sources = [{"archive_id": "s1"}, {"archive_id": "s2"}]
    eng.migrate_bytes(_blob(), archive_id="s1", filename="s1.tar.gz", cycle_date="2026-09-21")
    inv = eng.inventory(sources)
    assert inv["total_source_archives"] == 2
    assert inv["migrated_archives"] == 1
    assert inv["missing_archives"] == 1


def test_discover_local_sources(tmp_path):
    blob = _blob()
    p = tmp_path / "src" / "one.tar.gz"
    p.parent.mkdir(parents=True)
    p.write_bytes(blob)
    found = discover_local_sources(tmp_path / "src")
    assert len(found) == 1
    assert found[0]["sha256"] == sha256_bytes(blob)


def test_no_gdrive_backend_module_name():
    with pytest.raises(ImportError):
        from src.python.archive.gdrive_backend import GoogleDriveBackend  # noqa: F401


def test_secret_blocked_on_migrate(tmp_path):
    drive = DriveFsBackend(tmp_path / "d")
    eng = MigrationEngine(drive=drive, journal_path=tmp_path / "j.json")
    bad = b'{"client_secret": "abcdefghijklmnop_extra_padding_xx"}'
    rec = eng.migrate_bytes(bad, archive_id="sec", filename="credentials.json", cycle_date="2026-09-21")
    assert rec.status == MigrationStatus.FAILED.value
    assert rec.error_code == "SECRET_DETECTED"
