"""Market structure SSOT — instrument, session, price limits, eligibility."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class MarketStructure(str, Enum):
    CONTINUOUS = "CONTINUOUS"
    FCA = "FCA"
    HALTED = "HALTED"
    SUSPENDED = "SUSPENDED"
    UNKNOWN = "UNKNOWN"


class TradingSession(str, Enum):
    CLOSED = "CLOSED"
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    PRE_CLOSE = "PRE_CLOSE"
    CLOSE = "CLOSE"
    AUCTION = "AUCTION"
    UNKNOWN = "UNKNOWN"


class InstrumentEligibility(str, Enum):
    LISTED = "LISTED"
    ACTIVE = "ACTIVE"
    TRADEABLE = "TRADEABLE"
    SUSPENDED = "SUSPENDED"
    FCA = "FCA"
    HALTED = "HALTED"
    DELISTED = "DELISTED"
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
    TRADING_HALT = "TRADING_HALT"
    MARKET_STATUS_UNAVAILABLE = "MARKET_STATUS_UNAVAILABLE"
    SESSION_NOT_CONTINUOUS = "SESSION_NOT_CONTINUOUS"
    SESSION_UNKNOWN = "SESSION_UNKNOWN"
    PRICE_ABOVE_AR_LIMIT = "PRICE_ABOVE_AR_LIMIT"
    PRICE_BELOW_AR_LIMIT = "PRICE_BELOW_AR_LIMIT"
    PRICE_NOT_ON_TICK = "PRICE_NOT_ON_TICK"
    INVALID_LOT = "INVALID_LOT"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    NOT_TRADEABLE = "NOT_TRADEABLE"
    DELISTED = "DELISTED"
    MISSING_PRICE_RULES = "MISSING_PRICE_RULES"


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
    metadata_version: str = "ms_v2"
    session: TradingSession = TradingSession.UNKNOWN
    eligibility: InstrumentEligibility = InstrumentEligibility.UNKNOWN

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["structure"] = self.structure.value if isinstance(self.structure, Enum) else str(self.structure)
        d["session"] = self.session.value if isinstance(self.session, Enum) else str(self.session)
        d["eligibility"] = self.eligibility.value if isinstance(self.eligibility, Enum) else str(self.eligibility)
        return d

    @staticmethod
    def unknown(symbol: str, *, source: str = "none", as_of: str = "") -> "MarketStructureSnapshot":
        return MarketStructureSnapshot(
            symbol=symbol.upper(),
            structure=MarketStructure.UNKNOWN,
            as_of=as_of or datetime.now(timezone.utc).isoformat(),
            source=source,
            version="0",
            session=TradingSession.UNKNOWN,
            eligibility=InstrumentEligibility.UNKNOWN,
        )


@dataclass(frozen=True)
class PriceRules:
    symbol: str
    tick_size: float
    lot_size: int = 100
    ara: Optional[float] = None
    arb: Optional[float] = None
    as_of: str = ""
    source: str = "ops_metadata"
    version: str = "1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: int
    price: float
    quantity: int
    signal_id: str = ""


@dataclass(frozen=True)
class StructureGateResult:
    allow: bool
    reason: BlockReason
    symbol: str
    market_mode: str
    detected_at: str
    source: str
    detail: str = ""
    policy: str = "MARKET_STRUCTURE_SAFETY"
    session: str = ""
    eligibility: str = ""
    normalized_price: Optional[float] = None
    normalized_qty: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow": self.allow,
            "reason": self.reason.value if isinstance(self.reason, Enum) else str(self.reason),
            "symbol": self.symbol,
            "market_mode": self.market_mode,
            "session": self.session,
            "eligibility": self.eligibility,
            "detected_at": self.detected_at,
            "source": self.source,
            "detail": self.detail,
            "policy": self.policy,
            "normalized_price": self.normalized_price,
            "normalized_qty": self.normalized_qty,
            "order_broker": "NOT_SENT",
            "live_execution": False,
            "broker_execution": False,
        }
