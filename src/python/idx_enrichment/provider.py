"""Local-cache IDX enrichment provider — no live website scrape as production SSOT.

Load optional JSON cache:
{
  "as_of": "2026-09-24",
  "corporate_actions": [ {...} ],
  "liquidity": { "BBCA": {...} },
  "sectors": { "BBCA": {"sector": "...", "subsector": "..."} }
}

Env: IDX_ENRICHMENT_CACHE=/path/to/cache.json
Default path: data/idx/enrichment_cache.json
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from src.python.idx_enrichment.models import (
    CorporateActionEvent,
    CorporateActionType,
    LiquiditySnapshot,
    SectorSnapshot,
)


class IdxEnrichmentProvider:
    def __init__(
        self,
        *,
        corporate_actions: Optional[list[CorporateActionEvent]] = None,
        liquidity: Optional[dict[str, LiquiditySnapshot]] = None,
        sectors: Optional[dict[str, SectorSnapshot]] = None,
        as_of: str = "",
        source: str = "local_cache",
    ) -> None:
        self.corporate_actions = list(corporate_actions or [])
        self.liquidity = dict(liquidity or {})
        self.sectors = dict(sectors or {})
        self.as_of = as_of
        self.source = source

    def events_for(self, symbol: str) -> list[CorporateActionEvent]:
        sym = str(symbol).upper().strip()
        return [e for e in self.corporate_actions if str(e.symbol).upper() == sym]

    def liquidity_for(self, symbol: str) -> Optional[LiquiditySnapshot]:
        sym = str(symbol).upper().strip()
        return self.liquidity.get(sym)

    def sector_for(self, symbol: str) -> Optional[SectorSnapshot]:
        sym = str(symbol).upper().strip()
        return self.sectors.get(sym)

    def summary(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "source": self.source,
            "n_corporate_actions": len(self.corporate_actions),
            "n_liquidity": len(self.liquidity),
            "n_sectors": len(self.sectors),
            "live_scrape": False,
            "note": "IDX website is not production SSOT; use certified cache + provenance.",
        }

    @classmethod
    def from_cache_path(cls, path: Optional[str] = None) -> "IdxEnrichmentProvider":
        p = path or os.getenv("IDX_ENRICHMENT_CACHE") or "data/idx/enrichment_cache.json"
        fp = Path(p)
        if not fp.exists():
            return cls(as_of="", source="empty_cache")
        try:
            raw = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            return cls(as_of="", source="corrupt_cache")
        return cls.from_dict(raw if isinstance(raw, dict) else {})

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "IdxEnrichmentProvider":
        cas: list[CorporateActionEvent] = []
        for row in raw.get("corporate_actions") or []:
            if not isinstance(row, dict):
                continue
            try:
                at = CorporateActionType(str(row.get("action_type") or "OTHER").upper())
            except ValueError:
                at = CorporateActionType.OTHER
            cas.append(
                CorporateActionEvent(
                    symbol=str(row.get("symbol") or "").upper(),
                    action_type=at,
                    announcement_date=str(row.get("announcement_date") or ""),
                    cum_date=str(row.get("cum_date") or ""),
                    ex_date=str(row.get("ex_date") or ""),
                    record_date=str(row.get("record_date") or ""),
                    payment_date=str(row.get("payment_date") or ""),
                    effective_date=str(row.get("effective_date") or ""),
                    description=str(row.get("description") or ""),
                    source=str(row.get("source") or "idx_cache"),
                    provenance=str(row.get("provenance") or "local_cache"),
                    as_of=str(row.get("as_of") or raw.get("as_of") or ""),
                )
            )
        liq: dict[str, LiquiditySnapshot] = {}
        for sym, row in (raw.get("liquidity") or {}).items():
            if not isinstance(row, dict):
                continue
            s = str(sym).upper()
            liq[s] = LiquiditySnapshot(
                symbol=s,
                as_of=str(row.get("as_of") or raw.get("as_of") or ""),
                avg_volume=float(row.get("avg_volume") or 0),
                avg_value=float(row.get("avg_value") or 0),
                trading_frequency=float(row.get("trading_frequency") or 0),
                trading_days=int(row.get("trading_days") or 0),
                market_cap=float(row.get("market_cap") or 0),
                source=str(row.get("source") or "idx_cache"),
                provenance=str(row.get("provenance") or "local_cache"),
            )
        sec: dict[str, SectorSnapshot] = {}
        for sym, row in (raw.get("sectors") or {}).items():
            if not isinstance(row, dict):
                continue
            s = str(sym).upper()
            sec[s] = SectorSnapshot(
                symbol=s,
                sector=str(row.get("sector") or ""),
                subsector=str(row.get("subsector") or ""),
                industry=str(row.get("industry") or ""),
                as_of=str(row.get("as_of") or raw.get("as_of") or ""),
                source=str(row.get("source") or "idx_cache"),
                provenance=str(row.get("provenance") or "local_cache"),
            )
        return cls(
            corporate_actions=cas,
            liquidity=liq,
            sectors=sec,
            as_of=str(raw.get("as_of") or ""),
            source=str(raw.get("source") or "local_cache"),
        )


_default_provider: Optional[IdxEnrichmentProvider] = None


def get_default_provider() -> IdxEnrichmentProvider:
    global _default_provider
    if _default_provider is None:
        _default_provider = IdxEnrichmentProvider.from_cache_path()
    return _default_provider


def set_default_provider(p: Optional[IdxEnrichmentProvider]) -> None:
    global _default_provider
    _default_provider = p
