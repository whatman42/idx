from __future__ import annotations
from pathlib import Path
from typing import Optional

def find_production_version(directory: Path | str, model_id: str) -> Optional[str]:
    ptr = Path(directory) / f"{model_id}.PRODUCTION"
    if not ptr.exists():
        return None
    return ptr.read_text().strip() or None

def promote_to_production(directory: Path | str, model_id: str, model_version: str) -> None:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    ptr = directory / f"{model_id}.PRODUCTION"
    tmp = directory / f"{model_id}.PRODUCTION.tmp"
    tmp.write_text(model_version)
    tmp.replace(ptr)
