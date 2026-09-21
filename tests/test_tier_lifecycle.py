"""Tiered cold storage lifecycle — promote, never wipe last copy."""
from __future__ import annotations

from src.python.archive.integrity import make_tar_gz, sha256_bytes
from src.python.archive.migration import MigrationStatus
from src.python.archive.tier_plan import operational_archive_status, plan_tier1_promotions
from src.python.archive.tiers import (
    DrivePool,
    StorageTier,
    TierLifecycleEngine,
    TierPromotionPolicy,
)


def _blob(tag: bytes = b"v1") -> bytes:
    return make_tar_gz({"x.json": tag})


def test_promote_to_drive_keeps_source_flag(tmp_path):
    pool = DrivePool()
    pool.register("drive_01", tmp_path / "d1", capacity_limit_bytes=50_000_000, priority=10)
    eng = TierLifecycleEngine(pool=pool, journal_path=tmp_path / "j.json")
    data = _blob()
    r = eng.promote_to_drive(data, archive_id="A1", filename="A1.tar.gz", cycle_date="2026-09-21")
    assert r["status"] == MigrationStatus.MIGRATED.value
    assert r["deleted_source"] is False
    assert r["target_storage_id"] == "drive_01"
    assert r["source_sha256"] == r["target_sha256"]


def test_select_drive_by_capacity_and_priority(tmp_path):
    pool = DrivePool()
    pool.register("drive_01", tmp_path / "d1", capacity_limit_bytes=100, priority=10)
    pool.register("drive_02", tmp_path / "d2", capacity_limit_bytes=50_000_000, priority=20)
    eng = TierLifecycleEngine(pool=pool, journal_path=tmp_path / "j.json")
    data = _blob(b"big-enough")
    r = eng.promote_to_drive(data, archive_id="B1", filename="B1.tar.gz", cycle_date="2026-09-21")
    assert r["status"] == MigrationStatus.MIGRATED.value
    if len(data) > 100:
        assert r["target_storage_id"] == "drive_02"


def test_no_capacity_fails_without_delete(tmp_path):
    pool = DrivePool()
    pool.register("drive_01", tmp_path / "d1", capacity_limit_bytes=10, priority=1)
    eng = TierLifecycleEngine(pool=pool, journal_path=tmp_path / "j.json")
    r = eng.promote_to_drive(_blob(), archive_id="C1", filename="C1.tar.gz", cycle_date="2026-09-21")
    assert r["status"] == MigrationStatus.FAILED.value
    assert r["error_code"] == "NO_DRIVE_CAPACITY"
    assert r["deleted_source"] is False


def test_may_release_requires_verified_copies(tmp_path):
    pool = DrivePool()
    pool.register("drive_01", tmp_path / "d1", priority=1)
    eng = TierLifecycleEngine(
        pool=pool,
        journal_path=tmp_path / "j.json",
        policy=TierPromotionPolicy(min_copies_before_release=1),
    )
    data = _blob()
    eng.promote_to_drive(data, archive_id="R1", filename="R1.tar.gz", cycle_date="2026-09-21")
    decision = eng.may_release_from_tier1("R1", sha256_bytes(data))
    assert decision["release_allowed"] is True
    assert decision["verified_copies_in_pool"] >= 1


def test_drive_to_drive_rotation_deletes_source_only_after_verify(tmp_path):
    pool = DrivePool()
    pool.register("drive_01", tmp_path / "d1", capacity_limit_bytes=50_000_000, priority=10)
    pool.register("drive_02", tmp_path / "d2", capacity_limit_bytes=50_000_000, priority=20)
    eng = TierLifecycleEngine(pool=pool, journal_path=tmp_path / "j.json")
    data = _blob(b"rotate")
    eng.promote_to_drive(data, archive_id="D1", filename="D1.tar.gz", cycle_date="2026-09-20")
    r = eng.promote_between_drives("D1", from_storage_id="drive_01", to_storage_id="drive_02")
    assert r["status"] == MigrationStatus.MIGRATED.value
    assert r["to_storage_id"] == "drive_02"
    assert r["deleted_source"] is True
    assert pool.backends["drive_01"].find_by_archive_id("D1") is None
    assert pool.backends["drive_02"].find_by_archive_id("D1") is not None
    assert r["source_sha256"] == r["target_sha256"]


def test_inventory_tiers(tmp_path):
    pool = DrivePool()
    pool.register("drive_01", tmp_path / "d1")
    eng = TierLifecycleEngine(pool=pool, journal_path=tmp_path / "j.json")
    eng.promote_to_drive(_blob(), archive_id="I1", filename="I1.tar.gz", cycle_date="2026-09-21")
    inv = eng.inventory_tiers([{"archive_id": "I1"}, {"archive_id": "I2"}])
    assert inv["tier1_sources"] == 2
    assert inv["verified_drive_copies"] >= 1
    assert inv["policy"]["rule"] == "never_delete_until_verified_copy_elsewhere"


def test_github_tier1_never_auto_decommissioned(tmp_path):
    pool = DrivePool()
    pool.register("drive_01", tmp_path / "d1")
    eng = TierLifecycleEngine(pool=pool, journal_path=tmp_path / "j.json")
    for i in range(3):
        r = eng.promote_to_drive(
            _blob(f"v{i}".encode()),
            archive_id=f"G{i}",
            filename=f"G{i}.tar.gz",
            cycle_date=f"2026-09-{20+i:02d}",
            source_tier=StorageTier.GITHUB_TIER1.value,
        )
        assert r["deleted_source"] is False


def test_plan_tier1_promotions_threshold_not_deletion(tmp_path):
    pool = DrivePool()
    pool.register("drive_01", tmp_path / "d1", capacity_limit_bytes=50_000_000, priority=1)
    tier1 = [
        {"archive_id": "old1", "size_bytes": 1000, "created_at": "2026-09-01T00:00:00Z"},
        {"archive_id": "old2", "size_bytes": 1000, "created_at": "2026-09-02T00:00:00Z"},
        {"archive_id": "new3", "size_bytes": 1000, "created_at": "2026-09-20T00:00:00Z"},
    ]
    plan = plan_tier1_promotions(tier1, pool=pool, max_tier1=2)
    assert plan["threshold_exceeded"] is True
    assert plan["overflow_count"] == 1
    assert plan["promote_plan"][0]["archive_id"] == "old1"
    assert plan["promote_plan"][0]["delete_tier1_after"] is False
    assert plan["deleted_source"] is False
    assert plan["rule"] == "threshold_triggers_promotion_not_deletion"


def test_operational_status_declares_no_github_decommission(tmp_path):
    pool = DrivePool()
    pool.register("drive_01", tmp_path / "d1")
    st = operational_archive_status(pool=pool)
    assert st["github_decommission"] is False
    assert st["github_tier1"] == "ACTIVE"
    assert st["live_execution"] is False
    assert "live_colab_multi_account" in st["ci_does_not_prove"]
