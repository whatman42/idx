#!/usr/bin/env python3
"""Real Google Drive cold-archive certification — never prints secrets."""
from __future__ import annotations

import os
import sys
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


def main() -> int:
    raw = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        print("CREDENTIAL_PRESENT=false")
        print("REAL GDRIVE CLOUD = NOT EXECUTED")
        return 2
    print("CREDENTIAL_PRESENT=true")

    from src.python.archive.gdrive_backend import GoogleDriveBackend
    from src.python.archive.manager import ArchiveManager
    from src.python.archive.integrity import sha256_bytes
    from src.python.archive.contracts import ArchiveStatus

    backend = GoogleDriveBackend.from_env()
    if not backend.available():
        print(f"[FAIL] auth error={backend.last_error}")
        print("REAL GDRIVE CLOUD = FAIL")
        return 1
    print("[PASS] authentication")

    ns = f"cloud_certification/{uuid.uuid4().hex[:12]}"
    data = f"gdrive-cert-payload-{ns}".encode()
    h = sha256_bytes(data)
    m = ArchiveManager(prefer_gdrive=True, gdrive_backend=backend)
    r = m.archive_bytes(data, artifact_id=ns, artifact_type="certification", source="gdrive_cert")
    if not (r.ok and r.remote_persisted and r.backend == "gdrive"):
        print(f"[FAIL] upload {r.to_dict()}")
        return 1
    print("[PASS] upload remote_persisted=true")

    r2 = m.archive_bytes(data, artifact_id=ns, artifact_type="certification", source="gdrive_cert")
    if not r2.idempotent:
        print(f"[FAIL] idempotency {r2.to_dict()}")
        return 1
    print("[PASS] idempotency")

    rest = m.restore(file_id=r.reference.drive_file_id, expected_hash=h)
    if not rest.ok or rest.status != ArchiveStatus.RESTORE_SUCCESS.value:
        print(f"[FAIL] restore {rest.to_dict()}")
        return 1
    print("[PASS] restore hash_match")

    miss = m.restore(file_id="nonexistent-file-id-000")
    if miss.ok:
        print("[FAIL] missing should not ok")
        return 1
    print("[PASS] missing_object handled")

    print("REAL GDRIVE CLOUD = PASS")
    print("GDRIVE COLD STORAGE CERTIFICATION = PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
