"""Market structure SSOT — FCA/HALT/UNKNOWN are not boolean flags."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MarketStructure(str, Enum):
    CONTINUOUS = "CONTINUOUS"
    FCA = "FCA"
    HALTED = "HALTED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class BlockReason(str, Enum):
    NONE = "NONE"
    FCA_INSTRUMENT = "FCA_INSTRUMENT"
    MARKET_STRUCTURE_UNKNOWN = "MARKET_STRUCTURE_UNKNOWN"
    MARKET_DATA_STALE = "MARKET_DATA_STALE"
    HALTED = "HALTED"
    SUSPENDED = "SUSPENDED"
    STRUCTURE_CHANGED = "STRUCTURE_CHANGED"
    MISSING_SNAPSHOT = "MISSING_SNAPSHOT"
    POLICY_BLOCK = "POLICY_BLOCK"


@dataclass(frozen=True)
class MarketStructureSnapshot:
    symbol: str
    structure: MarketStructure
    as_of: str
    source: str
    version: str = "1"
    board: str = ""
    trading_status: str = ""
    auction_mode: str = ""
    fca_session: str = ""
    effective_from: str = ""
    effective_until: str = ""
    metadata_version: str = "ms_v1"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["structure"] = self.structure.value if isinstance(self.structure, MarketStructure) else str(self.structure)
        return d

    @staticmethod
    def unknown(symbol: str, *, source: str = "none", as_of: str = "") -> "MarketStructureSnapshot":
        return MarketStructureSnapshot(
            symbol=symbol.upper(),
            structure=MarketStructure.UNKNOWN,
            as_of=as_of or datetime.now(timezone.utc).isoformat(),
            source=source,
            version="0",
        )


@dataclass(frozen=True)
class StructureGateResult:
    allow: bool
    reason: BlockReason
    symbol: str
    market_mode: str
    detected_at: str
    source: str
    detail: str = ""
    policy: str = "FCA_BLOCK"

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow": self.allow,
            "reason": self.reason.value if isinstance(self.reason, BlockReason) else str(self.reason),
            "symbol": self.symbol,
            "market_mode": self.market_mode,
            "detected_at": self.detected_at,
            "source": self.source,
            "detail": self.detail,
            "policy": self.policy,
            "order_broker": "NOT_SENT",
            "live_execution": False,
            "broker_execution": False,
        }
