"""Sector concentration helpers — risk/research plane."""
from __future__ import annotations

from typing import Mapping, Optional

from src.python.idx_enrichment.models import DataAuthority, EnrichmentDecision, SectorSnapshot

MAX_SECTOR_WEIGHT = 0.35


def sector_exposure(
    open_positions: Mapping[str, dict],
    sector_map: Mapping[str, SectorSnapshot],
    *,
    equity: float,
) -> dict[str, float]:
    if equity <= 0:
        return {}
    out: dict[str, float] = {}
    for sym, p in (open_positions or {}).items():
        if not isinstance(p, dict):
            continue
        qty = float(p.get("qty") or 0)
        avg = float(p.get("avg_entry") or p.get("entry_price") or 0)
        if qty <= 0 or avg <= 0:
            continue
        w = (qty * avg) / equity
        snap = sector_map.get(str(sym).upper()) or sector_map.get(str(sym))
        sector = (snap.sector if snap else "") or "UNKNOWN"
        out[sector] = out.get(sector, 0.0) + w
    return out


def evaluate_sector_add(
    symbol: str,
    proposed_weight: float,
    open_positions: Mapping[str, dict],
    sector_map: Mapping[str, SectorSnapshot],
    *,
    equity: float,
    max_sector_weight: float = MAX_SECTOR_WEIGHT,
) -> EnrichmentDecision:
    sym = str(symbol).upper().strip()
    snap = sector_map.get(sym)
    if snap is None or not snap.sector:
        return EnrichmentDecision(
            allow=True,
            reason="NO_SECTOR_DATA",
            layer="sector",
            authority=DataAuthority.RISK_GATE.value,
            detail="sector unknown — pass",
            symbols_affected=[sym],
        )
    exp = sector_exposure(open_positions, sector_map, equity=equity)
    projected = exp.get(snap.sector, 0.0) + max(0.0, float(proposed_weight))
    if projected > max_sector_weight + 1e-9:
        return EnrichmentDecision(
            allow=False,
            reason="SKIPPED_SECTOR_CONCENTRATION",
            layer="sector",
            authority=DataAuthority.RISK_GATE.value,
            detail=f"sector={snap.sector} projected={projected:.3f}>{max_sector_weight:.3f}",
            symbols_affected=[sym],
        )
    return EnrichmentDecision(
        allow=True,
        reason="PASS",
        layer="sector",
        authority=DataAuthority.RISK_GATE.value,
        detail=f"sector={snap.sector} projected={projected:.3f}",
        symbols_affected=[sym],
    )
