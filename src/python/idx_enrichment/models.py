"""IDX enrichment SSOT models — corporate action, liquidity, sector, financial stubs.

Production path: local cache + provenance only. No live idx.co.id scrape as SSOT.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class DataAuthority(str, Enum):
    HARD_GATE = "HARD_GATE"           # block entry if violated
    CONDITIONAL_GATE = "CONDITIONAL_GATE"
    RISK_GATE = "RISK_GATE"
    RESEARCH = "RESEARCH"
    INFORMATIONAL = "INFORMATIONAL"


class CorporateActionType(str, Enum):
    DIVIDEND = "DIVIDEND"
    STOCK_SPLIT = "STOCK_SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    RIGHTS_ISSUE = "RIGHTS_ISSUE"
    WARRANT = "WARRANT"
    ADDITIONAL_SHARES = "ADDITIONAL_SHARES"
    OTHER = "OTHER"


class EventGuardDecision(str, Enum):
    PASS = "PASS"
    DATA_EVENT_REVIEW = "DATA_EVENT_REVIEW"
    NO_DATA = "NO_DATA"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class CorporateActionEvent:
    symbol: str
    action_type: CorporateActionType
    announcement_date: str = ""
    cum_date: str = ""
    ex_date: str = ""
    record_date: str = ""
    payment_date: str = ""
    effective_date: str = ""
    description: str = ""
    source: str = "idx_cache"
    provenance: str = "local_cache"
    as_of: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action_type"] = self.action_type.value
        return d


@dataclass(frozen=True)
class LiquiditySnapshot:
    symbol: str
    as_of: str
    avg_volume: float = 0.0
    avg_value: float = 0.0
    trading_frequency: float = 0.0
    trading_days: int = 0
    market_cap: float = 0.0
    source: str = "idx_cache"
    provenance: str = "local_cache"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SectorSnapshot:
    symbol: str
    sector: str = ""
    subsector: str = ""
    industry: str = ""
    as_of: str = ""
    source: str = "idx_cache"
    provenance: str = "local_cache"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class FinancialSnapshot:
    """Research-only. Requires publication_timestamp for PIT; period_end alone is insufficient."""
    symbol: str
    period_end: str = ""
    publication_timestamp: str = ""
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    assets: Optional[float] = None
    liabilities: Optional[float] = None
    equity: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    source: str = "xbrl_stub"
    provenance: str = "research_only"
    authority: str = DataAuthority.RESEARCH.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EnrichmentDecision:
    allow: bool
    reason: str
    layer: str
    authority: str
    detail: str = ""
    symbols_affected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
