#!/usr/bin/env python3
"""Cold archive certification — local and optional GitHub Release."""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("local", "github_release"), default="local")
    args = ap.parse_args()

    from src.python.archive.manager import ArchiveManager
    from src.python.archive.contracts import ArchiveStatus

    out = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "idx_cold_cert_out"
    out.mkdir(parents=True, exist_ok=True)
    local_root = Path(os.environ.get("IDX_ARCHIVE_LOCAL_ROOT", "/tmp/idx_cold_archive"))

    ns = f"cloud_certification/{uuid.uuid4().hex[:10]}"
    files = {
        "sample.json": json.dumps({"ns": ns, "ok": True}, sort_keys=True).encode(),
        "sample.csv": b"a,b\n1,2\n",
    }
    prefer = args.mode == "github_release"
    m = ArchiveManager(local_root=local_root, prefer_github_release=prefer)
    tag = f"idx-archive-cert-{uuid.uuid4().hex[:8]}"

    r1 = m.archive_files(
        files, artifact_id=ns, artifact_type="certification",
        source="cold_archive_cert", release_tag=tag,
    )
    print(f"[INFO] first status={r1.status} backend={r1.backend} ok={r1.ok}")
    if not r1.ok:
        print("CERTIFICATION = FAIL (first archive)")
        return 1
    print("[PASS] create+compress+hash")

    r2 = m.archive_files(
        files, artifact_id=ns, artifact_type="certification",
        source="cold_archive_cert", release_tag=tag,
    )
    if not r2.idempotent and r2.status != ArchiveStatus.ARCHIVE_ALREADY_PRESENT.value:
        print(f"[FAIL] idempotency {r2.to_dict()}")
        return 1
    print("[PASS] idempotency")

    r3 = m.archive_files(
        {"sample.json": b'{"changed":true}'}, artifact_id=ns,
        artifact_type="certification", release_tag=tag,
    )
    if r3.status == ArchiveStatus.ARCHIVE_CONFLICT.value:
        print("[PASS] conflict detection")
    elif args.mode == "local":
        print(f"[FAIL] expected CONFLICT got {r3.status}")
        return 1

    r4 = m.archive_files(
        {"x.env": b"TURSO_AUTH_TOKEN=supersecretvalue123"},
        artifact_id=f"{ns}-secret", artifact_type="certification",
    )
    if r4.status != ArchiveStatus.ARCHIVE_BLOCKED_SECRET_DETECTED.value:
        print(f"[FAIL] secret scan {r4.status}")
        return 1
    print("[PASS] secret blocked")

    if r1.reference and r1.reference.local_path:
        rest = m.restore(
            identity=r1.reference.archive_identity,
            expected_archive_sha256=r1.reference.archive_sha256,
            dest_dir=out / "restore",
        )
        if not rest.ok:
            print(f"[FAIL] restore {rest.to_dict()}")
            return 1
        print("[PASS] restore+sha256")

    (out / "cert_report.json").write_text(
        json.dumps({"mode": args.mode, "status": "PASS", "backend": r1.backend}, indent=2),
        encoding="utf-8",
    )
    print("COLD ARCHIVE CERTIFICATION = PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
