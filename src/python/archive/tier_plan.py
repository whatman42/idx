"""Tier-1 threshold planning — promotion without deletion (archive plane only)."""
from __future__ import annotations

from typing import Any, Optional

from src.python.archive.tiers import DrivePool


def plan_tier1_promotions(
    tier1_archives: list[dict[str, Any]],
    *,
    pool: Optional[DrivePool] = None,
    max_tier1: int = 20,
) -> dict[str, Any]:
    """When Tier-1 count exceeds threshold, list oldest eligible for Drive promotion.

    GitHub capacity pressure → promote (copy-forward), never auto-delete Tier-1.
    """
    n = len(tier1_archives)
    limit = int(max_tier1)

    def sort_key(a: dict[str, Any]) -> tuple:
        return (str(a.get("created_at") or a.get("cycle_date") or ""), str(a.get("archive_id") or ""))

    ordered = sorted(tier1_archives, key=sort_key)
    overflow = max(0, n - limit)
    eligible = ordered[:overflow] if overflow else []
    planned = []
    for a in eligible:
        size = int(a.get("size_bytes") or 0)
        target = ""
        if pool is not None:
            target = pool.select_target(size if size > 0 else 1) or ""
        planned.append(
            {
                "archive_id": a.get("archive_id"),
                "size_bytes": size,
                "proposed_target": target,
                "action": "PROMOTE_TO_DRIVE" if (pool is None or target) else "BLOCKED_NO_CAPACITY",
                "delete_tier1_after": False,
            }
        )
    return {
        "tier1_count": n,
        "max_tier1": limit,
        "threshold_exceeded": overflow > 0,
        "overflow_count": overflow,
        "promote_plan": planned,
        "rule": "threshold_triggers_promotion_not_deletion",
        "deleted_source": False,
    }


def operational_archive_status(*, pool: Optional[DrivePool] = None) -> dict[str, Any]:
    return {
        "archive_plane": "TIERED_COLD_STORAGE",
        "github_tier1": "ACTIVE",
        "drive_pool": "ACTIVE" if (pool and pool.backends) else "CONFIGURED_EMPTY",
        "tier_promotion": "IMPLEMENTED",
        "sha256": "ENFORCED",
        "fail_closed": True,
        "github_decommission": False,
        "live_execution": False,
        "broker_execution": False,
        "production_mutation": False,
        "ci_proves": "lifecycle_engine_invariants",
        "ci_does_not_prove": "live_colab_multi_account_drive_auth_transfer",
        "pool_members": list(pool.meta.keys()) if pool else [],
    }
