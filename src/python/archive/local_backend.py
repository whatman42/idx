"""Local filesystem cold archive backend (tests + offline fallback)."""
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
        self._index_path.write_text(json.dumps(self._index, sort_keys=True, indent=2), encoding="utf-8")

    def put(
        self,
        *,
        logical_id: str,
        data: bytes,
        content_hash: str,
        meta: dict,
        folder_key: str,
    ) -> dict:
        if logical_id in self._index and self._index[logical_id].get("content_hash") == content_hash:
            return {**self._index[logical_id], "idempotent": True}
        dest_dir = self.root / folder_key
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{content_hash[:16]}_{logical_id.replace('/', '_')}.bin"
        dest.write_bytes(data)
        man = dest.with_suffix(".manifest.json")
        record = {
            "logical_id": logical_id,
            "content_hash": content_hash,
            "size_bytes": len(data),
            "path": str(dest),
            "folder_key": folder_key,
            "meta": meta,
            "file_id": f"local:{content_hash[:24]}",
            "folder_id": f"local-folder:{folder_key}",
            "idempotent": False,
        }
        man.write_text(json.dumps(record, sort_keys=True, indent=2), encoding="utf-8")
        self._index[logical_id] = record
        self._save_index()
        return record

    def get(self, *, file_id: str = "", logical_id: str = "") -> Optional[tuple[bytes, dict]]:
        rec = None
        if logical_id and logical_id in self._index:
            rec = self._index[logical_id]
        elif file_id:
            for r in self._index.values():
                if r.get("file_id") == file_id:
                    rec = r
                    break
        if not rec:
            return None
        data = Path(rec["path"]).read_bytes()
        if sha256_bytes(data) != rec["content_hash"]:
            raise ValueError("ARCHIVE_INTEGRITY_FAILURE")
        return data, rec

    def available(self) -> bool:
        return True
