"""Market structure metadata provider — no permanent FCA list in strategy logic."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Optional

from src.python.market_structure.models import MarketStructure, MarketStructureSnapshot


class MarketStructureProvider:
    def __init__(
        self,
        records: Optional[Mapping[str, MarketStructureSnapshot]] = None,
        *,
        default_structure: MarketStructure = MarketStructure.UNKNOWN,
    ) -> None:
        self._records = {k.upper(): v for k, v in (records or {}).items()}
        self._default = default_structure

    def get(self, symbol: str) -> MarketStructureSnapshot:
        sym = (symbol or "").upper()
        if sym in self._records:
            return self._records[sym]
        return MarketStructureSnapshot.unknown(sym, source="provider_miss")

    def upsert(self, snapshot: MarketStructureSnapshot) -> None:
        self._records[snapshot.symbol.upper()] = snapshot

    @staticmethod
    def from_status_map(
        status_map: Mapping[str, str],
        *,
        source: str = "ops_metadata",
        version: str = "1",
        as_of: str = "",
    ) -> "MarketStructureProvider":
        as_of = as_of or datetime.now(timezone.utc).isoformat()
        records = {}
        for sym, st in status_map.items():
            try:
                structure = MarketStructure(str(st).upper())
            except ValueError:
                structure = MarketStructure.UNKNOWN
            records[sym.upper()] = MarketStructureSnapshot(
                symbol=sym.upper(),
                structure=structure,
                as_of=as_of,
                source=source,
                version=version,
            )
        return MarketStructureProvider(records)
