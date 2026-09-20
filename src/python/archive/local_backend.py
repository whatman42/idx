"""Local filesystem cold archive backend (staging + offline)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.python.archive.integrity import sha256_bytes


class LocalArchiveBackend:
    name = "local"

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "manifest_index.json"
        self._index: dict[str, dict] = {}
        if self._index_path.exists():
            try:
                self._index = json.loads(self._index_path.read_text(encoding="utf-8"))
            except Exception:
                self._index = {}

    def _save_index(self) -> None:
        self._index_path.write_text(
            json.dumps(self._index, sort_keys=True, indent=2), encoding="utf-8"
        )

    def find_by_identity(self, identity: str) -> Optional[dict]:
        return self._index.get(identity)

    def find_by_artifact_id(self, artifact_id: str) -> list[dict]:
        return [r for r in self._index.values() if r.get("artifact_id") == artifact_id]

    def put(
        self,
        *,
        identity: str,
        artifact_id: str,
        content_sha256: str,
        archive_bytes: bytes,
        archive_sha256: str,
        meta: dict,
        folder_key: str,
    ) -> dict:
        existing = self._index.get(identity)
        if existing and existing.get("archive_sha256") == archive_sha256:
            return {**existing, "idempotent": True, "status": "ARCHIVE_ALREADY_PRESENT"}
        for r in self.find_by_artifact_id(artifact_id):
            if r.get("content_sha256") != content_sha256 and r.get("identity") != identity:
                return {
                    "status": "ARCHIVE_CONFLICT",
                    "artifact_id": artifact_id,
                    "existing_identity": r.get("identity"),
                    "idempotent": False,
                }
        dest_dir = self.root / folder_key
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{archive_sha256[:16]}.tar.gz"
        dest.write_bytes(archive_bytes)
        (dest_dir / f"{archive_sha256[:16]}.tar.gz.sha256").write_text(
            f"{archive_sha256}  {dest.name}\n", encoding="utf-8"
        )
        record = {
            "identity": identity,
            "artifact_id": artifact_id,
            "content_sha256": content_sha256,
            "archive_sha256": archive_sha256,
            "size_bytes": len(archive_bytes),
            "path": str(dest),
            "folder_key": folder_key,
            "meta": meta,
            "file_id": f"local:{archive_sha256[:24]}",
            "idempotent": False,
            "status": "ARCHIVE_SUCCESS",
        }
        self._index[identity] = record
        self._save_index()
        return record

    def get(self, *, file_id: str = "", identity: str = "") -> Optional[tuple[bytes, dict]]:
        rec = None
        if identity and identity in self._index:
            rec = self._index[identity]
        elif file_id:
            for r in self._index.values():
                if r.get("file_id") == file_id:
                    rec = r
                    break
        if not rec:
            return None
        data = Path(rec["path"]).read_bytes()
        if sha256_bytes(data) != rec["archive_sha256"]:
            raise ValueError("ARCHIVE_INTEGRITY_FAILURE")
        return data, rec

    def available(self) -> bool:
        return True
