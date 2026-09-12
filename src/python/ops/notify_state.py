from __future__ import annotations
import json
from pathlib import Path
from typing import Any

class NotifyStateStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.is_corrupt = False
        self._data: dict[str, Any] = {}
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
                if not isinstance(self._data, dict):
                    self.is_corrupt = True
                    self._data = {}
            except Exception:
                self.is_corrupt = True
                self._data = {}

    def was_notified(self, nid: str) -> bool:
        rec = self._data.get(nid) or {}
        return rec.get("status") in ("NOTIFIED", "ALREADY_NOTIFIED")

    def mark(self, nid: str, status: str, meta: dict | None = None) -> None:
        self._data[nid] = {"status": status, **(meta or {})}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=2, default=str))
        tmp.replace(self.path)
