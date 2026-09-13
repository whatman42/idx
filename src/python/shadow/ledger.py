"""Isolated shadow ledgers — separate from production paper portfolio."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


def shadow_dir(base: str | Path) -> Path:
    p = Path(base) / "shadow"
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_shadow_report(base: str | Path, report: dict[str, Any]) -> Path:
    d = shadow_dir(base)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = d / f"shadow_report_{ts}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    (d / "last_shadow_report.json").write_text(json.dumps(report, indent=2, default=str))
    return path


def load_governor_memory(base: str | Path) -> dict[str, Any]:
    p = shadow_dir(base) / "governor_utility_memory.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def save_governor_memory(base: str | Path, memory: dict[str, Any]) -> None:
    d = shadow_dir(base)
    p = d / "governor_utility_memory.json"
    p.write_text(json.dumps(memory, indent=2, default=str))
