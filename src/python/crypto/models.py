"""Crypto domain models — instruments, exclusions, provenance."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class ExclusionReason(str, Enum):
    INVALID_METADATA = "INVALID_METADATA"
    MARKET_INACTIVE = "MARKET_INACTIVE"
    OHLCV_UNAVAILABLE = "OHLCV_UNAVAILABLE"
    INVALID_PRECISION = "INVALID_PRECISION"
    INVALID_SYMBOL = "INVALID_SYMBOL"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    UNSUPPORTED_INSTRUMENT = "UNSUPPORTED_INSTRUMENT"
    NON_USDT_QUOTE = "NON_USDT_QUOTE"
    MISSING_FILTERS = "MISSING_FILTERS"


class InstrumentStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CryptoInstrument:
    symbol: str
    base_asset: str
    quote_asset: str
    market_status: str
    provider: str
    discovered_at: str
    price_precision: int = 8
    quantity_precision: int = 8
    min_quantity: float = 0.0
    min_notional: float = 0.0
    market_data_available: bool = True
    status: str = InstrumentStatus.ELIGIBLE.value
    block_reason: str = ""
    raw_symbol: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UniverseDiscoveryReport:
    universe_version: str
    discovery_timestamp: str
    provider: str
    discovered_count: int
    eligible_count: int
    blocked_count: int
    eligible: list[CryptoInstrument] = field(default_factory=list)
    blocked: list[CryptoInstrument] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "universe_version": self.universe_version,
            "discovery_timestamp": self.discovery_timestamp,
            "provider": self.provider,
            "discovered_count": self.discovered_count,
            "eligible_count": self.eligible_count,
            "blocked_count": self.blocked_count,
            "eligible_symbols": [i.symbol for i in self.eligible],
            "blocked": [
                {"symbol": i.symbol, "status": i.status, "reason": i.block_reason}
                for i in self.blocked
            ],
            "errors": list(self.errors),
            "live_scrape_orders": False,
            "base_currency": "USDT",
        }


@dataclass
class CryptoBar:
    symbol: str
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    provider: str = "binance_public"
    provenance: str = "MARKET_DATA_CRYPTO"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
