"""IDX equity universe loaders.

Default research universe is full listed set from public Wikipedia scrape
(NOT official BEI master file). Use for full-market scan / paper ops.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

_DEFAULT_PATH = Path(__file__).resolve().parents[3] / "data" / "universe" / "idx_symbols.json"

_FALLBACK = [
    "AALI", "ACES", "ADRO", "AKRA", "AMMN", "AMRT", "ANTM", "ARTO", "ASII",
    "BBCA", "BBNI", "BBRI", "BBTN", "BMRI", "BRIS", "BRPT", "BUKA", "CPIN",
    "EMTK", "EXCL", "GGRM", "GOTO", "HMSP", "ICBP", "INCO", "INDF", "INKP",
    "ITMG", "JPFA", "KLBF", "MAPI", "MDKA", "MEDC", "PGAS", "PTBA", "SMGR",
    "TLKM", "TOWR", "UNTR", "UNVR",
]


def load_universe(path: str | Path | None = None) -> list[str]:
    p = Path(path) if path else _DEFAULT_PATH
    if not p.exists():
        alt = Path("data/universe/idx_symbols.json")
        p = alt if alt.exists() else p
    if p.exists():
        data = json.loads(p.read_text())
        syms = [str(s).strip().upper() for s in data.get("symbols", [])]
        return sorted({s for s in syms if s})
    return list(_FALLBACK)


def resolve_symbols(symbols_arg: str | Sequence[str] | None, *, universe_path: str | None = None) -> list[str]:
    if symbols_arg is None:
        return load_universe(universe_path)
    if isinstance(symbols_arg, (list, tuple)):
        raw = ",".join(symbols_arg)
    else:
        raw = str(symbols_arg).strip()
    if not raw or raw.upper() in ("ALL", "FULL", "UNIVERSE", "*"):
        return load_universe(universe_path)
    parts = [p.strip().upper() for p in raw.replace(";", ",").split(",") if p.strip()]
    if len(parts) == 1 and parts[0] in ("ALL", "FULL", "UNIVERSE", "*"):
        return load_universe(universe_path)
    return parts


def universe_meta(path: str | Path | None = None) -> dict:
    p = Path(path) if path else _DEFAULT_PATH
    if not p.exists():
        p = Path("data/universe/idx_symbols.json")
    if p.exists():
        return json.loads(p.read_text())
    return {"source": "fallback_liquid_core", "count": len(_FALLBACK), "symbols": _FALLBACK}
