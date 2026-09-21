"""Market structure metadata provider — versioned maps, no permanent hardcode."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping, Optional

from src.python.market_structure.models import (
    InstrumentEligibility,
    MarketStructure,
    MarketStructureSnapshot,
    TradingSession,
)


class MarketStructureProvider:
    def __init__(self, records: Optional[Mapping[str, MarketStructureSnapshot]] = None) -> None:
        self._records = {k.upper(): v for k, v in (records or {}).items()}

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
        session: str = "OPEN",
        eligibility: str = "TRADEABLE",
    ) -> "MarketStructureProvider":
        as_of = as_of or datetime.now(timezone.utc).isoformat()
        try:
            sess = TradingSession(session.upper())
        except Exception:
            sess = TradingSession.UNKNOWN
        try:
            elig = InstrumentEligibility(eligibility.upper())
        except Exception:
            elig = InstrumentEligibility.UNKNOWN
        records = {}
        for sym, st in status_map.items():
            try:
                structure = MarketStructure(str(st).upper())
            except ValueError:
                structure = MarketStructure.UNKNOWN
            e = elig
            if structure == MarketStructure.FCA:
                e = InstrumentEligibility.FCA
            elif structure == MarketStructure.HALTED:
                e = InstrumentEligibility.HALTED
            elif structure == MarketStructure.SUSPENDED:
                e = InstrumentEligibility.SUSPENDED
            elif structure == MarketStructure.UNKNOWN:
                e = InstrumentEligibility.UNKNOWN
            records[sym.upper()] = MarketStructureSnapshot(
                symbol=sym.upper(),
                structure=structure,
                as_of=as_of,
                source=source,
                version=version,
                session=sess if structure == MarketStructure.CONTINUOUS else TradingSession.UNKNOWN,
                eligibility=e if structure != MarketStructure.CONTINUOUS else elig,
            )
        return MarketStructureProvider(records)
