"""Filesystem-backed Google Drive layout simulator for migration/tests.

NOT a trading dependency. Used by migration plane and Colab bridge.
Real Colab uses the same path layout under a mounted Drive root.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from src.python.archive.integrity import sha256_bytes


class DriveFsBackend:
    """Deterministic IDX/cold_archive/... layout under a root directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.cold = self.root / "IDX" / "cold_archive"
        self.cold.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cold / "archive_index.json"
        if not self.index_path.exists():
            self._save_index({"schema_version": 1, "archives": []})

    def available(self) -> bool:
        try:
            self.cold.mkdir(parents=True, exist_ok=True)
            return True
        except OSError:
            return False

    def _load_index(self) -> dict[str, Any]:
        try:
            return json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:
            return {"schema_version": 1, "archives": []}

    def _save_index(self, idx: dict[str, Any]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(idx, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.index_path)

    def day_dir(self, cycle_date: str) -> Path:
        y, m, _ = cycle_date.split("-")
        d = self.cold / y / m / cycle_date
        (d / "archives").mkdir(parents=True, exist_ok=True)
        (d / "manifests").mkdir(parents=True, exist_ok=True)
        (d / "metadata").mkdir(parents=True, exist_ok=True)
        return d

    def find_by_archive_id(self, archive_id: str) -> Optional[dict[str, Any]]:
        for row in self._load_index().get("archives") or []:
            if row.get("archive_id") == archive_id:
                return dict(row)
        return None

    def find_by_sha256(self, sha256: str) -> Optional[dict[str, Any]]:
        for row in self._load_index().get("archives") or []:
            if row.get("sha256") == sha256:
                return dict(row)
        return None

    def list_archives(self) -> list[dict[str, Any]]:
        return list(self._load_index().get("archives") or [])

    def put(
        self,
        data: bytes,
        *,
        archive_id: str,
        cycle_date: str,
        filename: str,
        manifest: dict[str, Any],
    ) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("DRIVE_UNAVAILABLE")
        day = self.day_dir(cycle_date)
        path = day / "archives" / filename
        path.write_bytes(data)
        mpath = day / "manifests" / f"{archive_id}.json"
        mpath.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
        rel = str(path.relative_to(self.root)).replace("\\", "/")
        row = {**manifest, "drive_path": rel, "local_abs": str(path)}
        idx = self._load_index()
        archives = [a for a in (idx.get("archives") or []) if a.get("archive_id") != archive_id]
        archives.append(row)
        idx["archives"] = archives
        self._save_index(idx)
        return row

    def get_bytes(self, drive_path: str) -> bytes:
        p = self.root / drive_path
        if not p.is_file():
            raise FileNotFoundError(drive_path)
        return p.read_bytes()

    def delete(self, archive_id: str) -> bool:
        idx = self._load_index()
        archives = idx.get("archives") or []
        target = None
        rest = []
        for a in archives:
            if a.get("archive_id") == archive_id:
                target = a
            else:
                rest.append(a)
        if not target:
            return False
        for key in ("drive_path", "local_abs"):
            p = target.get(key)
            if p:
                path = Path(p) if Path(p).is_absolute() else self.root / p
                if path.is_file():
                    path.unlink()
        idx["archives"] = rest
        self._save_index(idx)
        return True

    def verify_file(self, drive_path: str, expected_sha256: str) -> bool:
        data = self.get_bytes(drive_path)
        return sha256_bytes(data) == expected_sha256
