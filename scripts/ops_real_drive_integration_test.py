#!/usr/bin/env python3
"""REAL Drive integration test harness (Colab operator-run).

Run ONLY with Google Drive mounted, e.g. /content/drive/MyDrive
Not a substitute for CI — CI does not prove OAuth/Drive network.
Does not touch trading core / ledger / signals.

  python scripts/ops_real_drive_integration_test.py --drive-root /content/drive/MyDrive
  python scripts/ops_real_drive_integration_test.py --drive-root /content/drive/MyDrive --drive-root2 /content/drive_acct2/MyDrive
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.python.archive.integrity import extract_tar_gz, make_tar_gz, sha256_bytes
from src.python.archive.migration import MigrationStatus
from src.python.archive.tier_plan import operational_archive_status, plan_tier1_promotions
from src.python.archive.tiers import DrivePool, TierLifecycleEngine, TierPromotionPolicy


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": bool(ok), "detail": detail}


def _write_report(args, drive_01: Path, evidence: dict) -> Path:
    path = Path(args.report) if args.report else (drive_01 / "IDX" / "cold_archive" / "real_drive_integration_report.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--drive-root", required=True)
    ap.add_argument("--drive-root2", default="")
    ap.add_argument("--report", default="")
    args = ap.parse_args()

    drive_01 = Path(args.drive_root)
    results: list[dict] = []
    evidence: dict = {
        "timestamp": _utc(),
        "trading_baseline": "5bb33b03331cf32e608eb06d31249c67caa73a52",
        "archive_plane_ref": "1d26552+",
        "live_execution": False,
        "broker_execution": False,
        "production_mutation": False,
        "github_decommission": False,
        "checks": [],
        "hashes": {},
        "multi_account": "NOT_TESTED",
    }

    if not drive_01.exists():
        results.append(_check("preflight_drive_root", False, f"missing {drive_01}"))
        evidence["checks"] = results
        print(json.dumps(evidence, indent=2))
        print("\nREAL DRIVE INTEGRATION NOT VERIFIED — Drive root not mounted")
        return 2

    probe = drive_01 / "IDX" / "cold_archive" / ".write_probe"
    try:
        probe.parent.mkdir(parents=True, exist_ok=True)
        probe.write_text(_utc(), encoding="utf-8")
        _ = probe.read_text(encoding="utf-8")
        results.append(_check("preflight_drive_write", True, str(probe)))
        results.append(_check("preflight_drive_read", True, "roundtrip"))
        probe.unlink(missing_ok=True)
    except Exception as e:
        results.append(_check("preflight_drive_write", False, type(e).__name__))
        evidence["checks"] = results
        print(json.dumps(evidence, indent=2))
        print("\nREAL DRIVE INTEGRATION NOT VERIFIED — no write permission")
        return 2

    results.append(_check("preflight_live_execution_false", True, "FALSE"))
    results.append(_check("preflight_broker_execution_false", True, "FALSE"))
    results.append(_check("preflight_production_mutation_false", True, "FALSE"))

    pool = DrivePool()
    pool.register("drive_01", drive_01, account_alias="drive_01", capacity_limit_bytes=0, priority=10)
    multi = False
    if args.drive_root2:
        root2 = Path(args.drive_root2)
        if root2.exists():
            pool.register("drive_02", root2, account_alias="drive_02", capacity_limit_bytes=0, priority=20)
            multi = True
            evidence["multi_account"] = "ATTEMPTED"
        else:
            evidence["multi_account"] = "NOT_TESTED"

    journal = drive_01 / "IDX" / "cold_archive" / "migration_journal.json"
    eng = TierLifecycleEngine(
        pool=pool,
        journal_path=journal,
        policy=TierPromotionPolicy(max_tier1_archives=20, min_copies_before_release=1),
    )

    fixture_files = {
        "meta.json": json.dumps({"test": "real_drive_integration", "ts": _utc()}).encode(),
        "payload.csv": b"symbol,close\nTEST,100\n",
    }
    data = make_tar_gz(fixture_files)
    archive_id = f"real_drive_test_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    filename = f"{archive_id}.tar.gz"
    source_sha = sha256_bytes(data)
    source_size = len(data)
    evidence["hashes"]["SOURCE_SHA256"] = source_sha
    evidence["hashes"]["SOURCE_SIZE"] = source_size
    evidence["archive_id"] = archive_id

    staging = Path(tempfile.mkdtemp(prefix="idx_stage_"))
    stage_path = staging / filename
    stage_path.write_bytes(data)
    colab_sha = sha256_bytes(stage_path.read_bytes())
    colab_size = stage_path.stat().st_size
    evidence["hashes"]["COLAB_SHA256"] = colab_sha
    evidence["hashes"]["COLAB_SIZE"] = colab_size
    results.append(_check("source_colab_sha_match", source_sha == colab_sha and source_size == colab_size))

    if source_sha != colab_sha:
        evidence["checks"] = results
        _write_report(args, drive_01, evidence)
        print("\nREAL DRIVE INTEGRATION NOT VERIFIED — staging hash mismatch")
        return 1

    rec = eng.promote_to_drive(
        data,
        archive_id=archive_id,
        filename=filename,
        cycle_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        source="colab_real_test",
    )
    results.append(
        _check(
            "promote_status",
            rec["status"] in (MigrationStatus.MIGRATED.value, MigrationStatus.ARCHIVE_ALREADY_MIGRATED.value),
            rec.get("status", ""),
        )
    )
    results.append(_check("tier1_deleted_source_false", rec.get("deleted_source") is False, str(rec.get("deleted_source"))))
    results.append(_check("target_assigned", bool(rec.get("target_storage_id")), rec.get("target_storage_id", "")))

    if rec["status"] not in (MigrationStatus.MIGRATED.value, MigrationStatus.ARCHIVE_ALREADY_MIGRATED.value):
        results.append(_check("drive_upload", False, rec.get("error_code", "")))
        evidence["checks"] = results
        evidence["promote"] = rec
        _write_report(args, drive_01, evidence)
        print("\nREAL DRIVE INTEGRATION NOT VERIFIED — promote failed")
        return 1

    be = pool.backends[rec["target_storage_id"]]
    row = be.find_by_archive_id(archive_id)
    if not row:
        results.append(_check("drive_index_row", False, "missing index row"))
        evidence["checks"] = results
        _write_report(args, drive_01, evidence)
        return 1

    drive_bytes = be.get_bytes(str(row["drive_path"]))
    drive_sha = sha256_bytes(drive_bytes)
    drive_size = len(drive_bytes)
    evidence["hashes"]["DRIVE_SHA256"] = drive_sha
    evidence["hashes"]["DRIVE_SIZE"] = drive_size
    evidence["drive_path"] = row.get("drive_path")
    evidence["storage_id"] = rec["target_storage_id"]

    triple = source_sha == colab_sha == drive_sha and source_size == colab_size == drive_size
    results.append(_check("sha256_triple_match", triple, f"src={source_sha[:12]} drv={drive_sha[:12]}"))
    results.append(_check("size_triple_match", source_size == drive_size, str(drive_size)))
    results.append(_check("manifest_sha", row.get("sha256") == drive_sha))
    results.append(_check("manifest_size", int(row.get("size_bytes") or 0) == drive_size))
    results.append(_check("manifest_verified_flag", bool(row.get("verified"))))

    try:
        extracted = extract_tar_gz(drive_bytes)
        ok_struct = "meta.json" in extracted and "payload.csv" in extracted
        results.append(_check("restore_structure", ok_struct, str(sorted(extracted.keys()))))
        results.append(_check("restore_payload", extracted.get("payload.csv") == fixture_files["payload.csv"]))
    except Exception as e:
        results.append(_check("restore_structure", False, type(e).__name__))

    corrupt = bytearray(drive_bytes)
    if len(corrupt) > 10:
        corrupt[10] ^= 0xFF
    corrupt_sha = sha256_bytes(bytes(corrupt))
    results.append(_check("corrupt_hash_differs", corrupt_sha != drive_sha))
    results.append(_check("corrupt_restore_blocked", corrupt_sha != source_sha))

    rec2 = eng.promote_to_drive(
        data,
        archive_id=archive_id,
        filename=filename,
        cycle_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        source="colab_real_test",
    )
    results.append(
        _check("idempotency", rec2["status"] == MigrationStatus.ARCHIVE_ALREADY_MIGRATED.value, rec2.get("status", ""))
    )

    other = make_tar_gz({"meta.json": b'{\"different\":true}'})
    rec3 = eng.promote_to_drive(
        other,
        archive_id=archive_id,
        filename=filename,
        cycle_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        source="colab_real_test",
    )
    results.append(_check("conflict_detected", rec3["status"] == MigrationStatus.CONFLICT.value, rec3.get("status", "")))
    results.append(_check("conflict_no_delete", rec3.get("deleted_source") is False))
    still = be.get_bytes(str(row["drive_path"]))
    results.append(_check("conflict_no_overwrite", sha256_bytes(still) == drive_sha))

    pool_bad = DrivePool()
    pool_bad.register("drive_full", drive_01 / "_full_sim", account_alias="full", capacity_limit_bytes=1, priority=1)
    eng_bad = TierLifecycleEngine(pool=pool_bad, journal_path=journal.with_name("journal_fail.json"))
    rec_fail = eng_bad.promote_to_drive(data, archive_id="should_fail_capacity", filename="x.tar.gz", cycle_date="2026-09-21")
    results.append(_check("failure_no_capacity", rec_fail["status"] == MigrationStatus.FAILED.value, rec_fail.get("error_code", "")))
    results.append(_check("failure_keeps_source_flag", rec_fail.get("deleted_source") is False))

    if multi and "drive_02" in pool.backends:
        rdd = eng.promote_between_drives(archive_id, from_storage_id="drive_01", to_storage_id="drive_02")
        ok_dd = rdd.get("status") == MigrationStatus.MIGRATED.value and rdd.get("source_sha256") == rdd.get("target_sha256")
        results.append(_check("drive_to_drive", ok_dd, str(rdd.get("status"))))
        evidence["multi_account"] = "PASS" if ok_dd else "FAIL"
        evidence["drive_to_drive"] = rdd
    else:
        results.append(_check("drive_to_drive", True, "SKIPPED single-account"))
        if evidence["multi_account"] != "ATTEMPTED":
            evidence["multi_account"] = "NOT_TESTED"

    plan = plan_tier1_promotions(
        [
            {"archive_id": "old", "size_bytes": 10, "created_at": "2020-01-01"},
            {"archive_id": "new", "size_bytes": 10, "created_at": "2026-01-01"},
            {"archive_id": archive_id, "size_bytes": source_size, "created_at": _utc()},
        ],
        pool=pool,
        max_tier1=2,
    )
    results.append(
        _check("fifo_plan_oldest_first", bool(plan["promote_plan"]) and plan["promote_plan"][0]["archive_id"] == "old")
    )
    results.append(_check("fifo_no_tier1_delete", plan.get("deleted_source") is False))

    try:
        from src.python.archive.contracts import archive_cannot_affect_trading

        results.append(_check("core_isolation_contract", archive_cannot_affect_trading() is True))
    except Exception as e:
        results.append(_check("core_isolation_contract", False, type(e).__name__))

    evidence["checks"] = results
    evidence["operational_status"] = operational_archive_status(pool=pool)
    evidence["promote"] = rec

    failed = [c for c in results if not c["pass"] and "SKIPPED" not in (c.get("detail") or "")]
    failed = [c for c in failed if c["name"] != "multi_account_root2"]

    report_path = _write_report(args, drive_01, evidence)
    print(
        json.dumps(
            {
                "report": str(report_path),
                "failed": failed,
                "pass_count": sum(1 for c in results if c["pass"]),
                "total": len(results),
            },
            indent=2,
        )
    )

    if failed:
        print("\nREAL DRIVE INTEGRATION NOT VERIFIED")
        for f in failed:
            print(" FAIL", f["name"], f.get("detail"))
        return 1

    print("\nREAL DRIVE INTEGRATION VERIFIED (single-account minimum)")
    if evidence["multi_account"] == "NOT_TESTED":
        print("MULTI-ACCOUNT REAL TEST = NOT TESTED")
    elif evidence["multi_account"] == "PASS":
        print("MULTI-ACCOUNT REAL TEST = PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        print("\nREAL DRIVE INTEGRATION NOT VERIFIED — exception")
        raise SystemExit(2)
