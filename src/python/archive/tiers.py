"""Tiered cold storage lifecycle — GitHub Tier-1 → Drive pool Tier-2+.

An archive is NEVER deleted from its current tier until a verified copy
exists in another tier. There is no "decommission GitHub" phase.

FIFO here means tier promotion of oldest eligible archives, not global wipe.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.python.archive.drive_fs_backend import DriveFsBackend
from src.python.archive.integrity import sha256_bytes
from src.python.archive.migration import MigrationEngine, MigrationStatus


class StorageTier(str, Enum):
    GITHUB_TIER1 = "GITHUB_TIER1"
    DRIVE_TIER2 = "DRIVE_TIER2"
    DRIVE_POOL = "DRIVE_POOL"


class StorageStatus(str, Enum):
    ACTIVE = "ACTIVE"
    NEAR_CAPACITY = "NEAR_CAPACITY"
    FULL = "FULL"
    DISABLED = "DISABLED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class StorageBackendMeta:
    storage_id: str
    provider: str
    account_alias: str = ""
    root_path: str = ""
    capacity_limit_bytes: int = 0
    used_capacity_bytes: int = 0
    priority: int = 100
    status: str = StorageStatus.ACTIVE.value
    tier: str = StorageTier.DRIVE_TIER2.value

    @property
    def available_capacity_bytes(self) -> int:
        if self.capacity_limit_bytes <= 0:
            return 2**63 - 1
        return max(0, self.capacity_limit_bytes - self.used_capacity_bytes)

    def near_capacity(self, threshold_ratio: float = 0.85) -> bool:
        if self.capacity_limit_bytes <= 0:
            return False
        return self.used_capacity_bytes >= int(self.capacity_limit_bytes * threshold_ratio)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["available_capacity_bytes"] = self.available_capacity_bytes
        return d


@dataclass
class ArchiveLocation:
    archive_id: str
    sha256: str
    size_bytes: int
    storage_id: str
    tier: str
    path: str = ""
    verified: bool = False
    created_at: str = ""
    cycle_date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DrivePool:
    backends: dict[str, DriveFsBackend] = field(default_factory=dict)
    meta: dict[str, StorageBackendMeta] = field(default_factory=dict)

    def register(
        self,
        storage_id: str,
        root: Path | str,
        *,
        account_alias: str = "",
        capacity_limit_bytes: int = 0,
        priority: int = 100,
    ) -> StorageBackendMeta:
        be = DriveFsBackend(root)
        m = StorageBackendMeta(
            storage_id=storage_id,
            provider="drive_fs",
            account_alias=account_alias or storage_id,
            root_path=str(root),
            capacity_limit_bytes=capacity_limit_bytes,
            priority=priority,
            tier=StorageTier.DRIVE_POOL.value,
        )
        used = sum(int(a.get("size_bytes") or 0) for a in be.list_archives())
        m.used_capacity_bytes = used
        if m.near_capacity():
            m.status = StorageStatus.NEAR_CAPACITY.value
        self.backends[storage_id] = be
        self.meta[storage_id] = m
        return m

    def select_target(self, size_bytes: int) -> Optional[str]:
        candidates = []
        for sid, m in self.meta.items():
            if m.status == StorageStatus.DISABLED.value:
                continue
            if m.available_capacity_bytes < size_bytes:
                continue
            if not self.backends[sid].available():
                continue
            candidates.append((m.priority, sid))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][1]

    def list_all_locations(self) -> list[ArchiveLocation]:
        out: list[ArchiveLocation] = []
        for sid, be in self.backends.items():
            m = self.meta[sid]
            for a in be.list_archives():
                out.append(
                    ArchiveLocation(
                        archive_id=str(a.get("archive_id") or ""),
                        sha256=str(a.get("sha256") or ""),
                        size_bytes=int(a.get("size_bytes") or 0),
                        storage_id=sid,
                        tier=m.tier,
                        path=str(a.get("drive_path") or ""),
                        verified=bool(a.get("verified")),
                        created_at=str(a.get("created_at") or ""),
                        cycle_date=str(a.get("cycle_id") or ""),
                    )
                )
        return out


@dataclass
class TierPromotionPolicy:
    max_tier1_archives: int = 20
    near_capacity_ratio: float = 0.85
    min_copies_before_release: int = 2


@dataclass
class TierLifecycleEngine:
    pool: DrivePool
    journal_path: Path
    policy: TierPromotionPolicy = field(default_factory=TierPromotionPolicy)
    source_commit: str = ""

    def __post_init__(self) -> None:
        self.journal_path = Path(self.journal_path)
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)

    def promote_to_drive(
        self,
        data: bytes,
        *,
        archive_id: str,
        filename: str = "",
        cycle_date: str = "",
        source_tier: str = StorageTier.GITHUB_TIER1.value,
        source: str = "github",
    ) -> dict[str, Any]:
        size = len(data)
        target_id = self.pool.select_target(size)
        if not target_id:
            return {
                "status": MigrationStatus.FAILED.value,
                "error_code": "NO_DRIVE_CAPACITY",
                "archive_id": archive_id,
                "source_tier": source_tier,
                "deleted_source": False,
            }
        be = self.pool.backends[target_id]
        eng = MigrationEngine(
            drive=be,
            journal_path=self.journal_path,
            source_commit=self.source_commit,
        )
        rec = eng.migrate_bytes(
            data,
            archive_id=archive_id,
            filename=filename or f"{archive_id}.tar.gz",
            cycle_date=cycle_date,
            source=source,
            extra_manifest={
                "source_tier": source_tier,
                "target_storage_id": target_id,
                "lifecycle": "TIER_PROMOTION",
            },
        )
        m = self.pool.meta[target_id]
        m.used_capacity_bytes = sum(int(a.get("size_bytes") or 0) for a in be.list_archives())
        if m.near_capacity(self.policy.near_capacity_ratio):
            m.status = StorageStatus.NEAR_CAPACITY.value

        return {
            "status": rec.status,
            "error_code": rec.error_code,
            "archive_id": archive_id,
            "source_tier": source_tier,
            "target_storage_id": target_id
            if rec.status
            in (
                MigrationStatus.MIGRATED.value,
                MigrationStatus.ARCHIVE_ALREADY_MIGRATED.value,
            )
            else "",
            "source_sha256": rec.source_sha256,
            "target_sha256": rec.target_sha256,
            "deleted_source": False,
            "drive_path": rec.drive_path,
        }

    def verified_copy_count(self, archive_id: str, sha256: str) -> int:
        n = 0
        for loc in self.pool.list_all_locations():
            if loc.archive_id == archive_id and loc.sha256 == sha256 and loc.verified:
                n += 1
        return n

    def may_release_from_tier1(self, archive_id: str, sha256: str) -> dict[str, Any]:
        copies = self.verified_copy_count(archive_id, sha256)
        allowed = copies >= self.policy.min_copies_before_release
        return {
            "archive_id": archive_id,
            "verified_copies_in_pool": copies,
            "min_required": self.policy.min_copies_before_release,
            "release_allowed": allowed,
            "note": "Caller must still keep recovery path; engine does not delete GitHub assets.",
        }

    def promote_between_drives(
        self,
        archive_id: str,
        *,
        from_storage_id: str,
        to_storage_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if from_storage_id not in self.pool.backends:
            return {"status": MigrationStatus.FAILED.value, "error_code": "UNKNOWN_SOURCE_STORAGE"}
        src = self.pool.backends[from_storage_id]
        row = src.find_by_archive_id(archive_id)
        if not row:
            return {"status": MigrationStatus.FAILED.value, "error_code": "NOT_FOUND"}
        data = src.get_bytes(str(row["drive_path"]))
        sha = sha256_bytes(data)
        if sha != row.get("sha256"):
            return {
                "status": MigrationStatus.FAILED.value,
                "error_code": "SOURCE_HASH_MISMATCH",
                "deleted_source": False,
            }

        size = len(data)
        target_id = to_storage_id or self.pool.select_target(size)
        if not target_id or target_id == from_storage_id:
            for sid in sorted(self.pool.backends.keys(), key=lambda s: self.pool.meta[s].priority):
                if sid != from_storage_id and self.pool.meta[sid].available_capacity_bytes >= size:
                    target_id = sid
                    break
        if not target_id or target_id == from_storage_id:
            return {
                "status": MigrationStatus.FAILED.value,
                "error_code": "NO_ALTERNATE_DRIVE",
                "deleted_source": False,
            }

        dst = self.pool.backends[target_id]
        eng = MigrationEngine(drive=dst, journal_path=self.journal_path, source_commit=self.source_commit)
        rec = eng.migrate_bytes(
            data,
            archive_id=archive_id,
            filename=str(row.get("filename") or f"{archive_id}.tar.gz"),
            cycle_date=str(row.get("cycle_id") or ""),
            source=f"drive:{from_storage_id}",
            extra_manifest={"lifecycle": "DRIVE_POOL_ROTATION", "from_storage_id": from_storage_id},
        )
        if rec.status not in (MigrationStatus.MIGRATED.value, MigrationStatus.ARCHIVE_ALREADY_MIGRATED.value):
            return {"status": rec.status, "error_code": rec.error_code, "deleted_source": False}

        release = False
        if rec.target_sha256 == sha and rec.source_sha256 == sha:
            found = dst.find_by_archive_id(archive_id)
            if found and found.get("verified"):
                src.delete(archive_id)
                release = True

        return {
            "status": MigrationStatus.MIGRATED.value,
            "archive_id": archive_id,
            "from_storage_id": from_storage_id,
            "to_storage_id": target_id,
            "source_sha256": sha,
            "target_sha256": rec.target_sha256,
            "deleted_source": release,
            "lifecycle": "DRIVE_POOL_ROTATION",
        }

    def inventory_tiers(self, tier1_sources: list[dict[str, Any]]) -> dict[str, Any]:
        locs = self.pool.list_all_locations()
        return {
            "tier1_sources": len(tier1_sources),
            "drive_locations": len(locs),
            "verified_drive_copies": sum(1 for L in locs if L.verified),
            "pool_members": list(self.pool.meta.keys()),
            "pool_meta": {k: v.to_dict() for k, v in self.pool.meta.items()},
            "policy": {
                "max_tier1_archives": self.policy.max_tier1_archives,
                "min_copies_before_release": self.policy.min_copies_before_release,
                "rule": "never_delete_until_verified_copy_elsewhere",
            },
        }
