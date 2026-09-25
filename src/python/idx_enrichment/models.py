"""IDX enrichment SSOT models — facts only; gates decide PASS/BLOCK/UNKNOWN.

Outcomes never include BUY/SELL/HOLD (not strategy authority).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class DataAuthority(str, Enum):
    HARD_GATE = "HARD_GATE"
    CONDITIONAL_GATE = "CONDITIONAL_GATE"
    RISK_GATE = "RISK_GATE"
    RESEARCH = "RESEARCH"
    INFORMATIONAL = "INFORMATIONAL"


class DataPresence(str, Enum):
    DATA_PRESENT = "DATA_PRESENT"
    NO_DATA = "NO_DATA"
    STALE = "STALE"
    INVALID = "INVALID"


class CorporateActionType(str, Enum):
    DIVIDEND = "DIVIDEND"
    STOCK_SPLIT = "STOCK_SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    RIGHTS_ISSUE = "RIGHTS_ISSUE"
    WARRANT = "WARRANT"
    ADDITIONAL_SHARES = "ADDITIONAL_SHARES"
    OTHER = "OTHER"


class CAOutcome(str, Enum):
    CA_CLEAR = "CA_CLEAR"
    CA_REVIEW = "CA_REVIEW"
    CA_BLOCK = "CA_BLOCK"


class GateOutcome(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"
    UNKNOWN = "UNKNOWN"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class Provenance:
    source: str = "idx_cache"
    as_of: str = ""
    retrieved_at: str = ""
    effective_from: str = ""
    effective_to: str = ""
    version: str = "1"
    symbol: str = ""
    status: str = "UNKNOWN"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
    provenance: Provenance = field(default_factory=Provenance)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["action_type"] = self.action_type.value
        if isinstance(self.provenance, Provenance):
            d["provenance"] = self.provenance.to_dict()
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
    provenance: Provenance = field(default_factory=Provenance)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(self.provenance, Provenance):
            d["provenance"] = self.provenance.to_dict()
        return d


@dataclass(frozen=True)
class SectorSnapshot:
    symbol: str
    sector: str = ""
    subsector: str = ""
    industry: str = ""
    as_of: str = ""
    provenance: Provenance = field(default_factory=Provenance)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if isinstance(self.provenance, Provenance):
            d["provenance"] = self.provenance.to_dict()
        return d


@dataclass(frozen=True)
class FinancialSnapshot:
    symbol: str
    period_end: str = ""
    publication_timestamp: str = ""
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    assets: Optional[float] = None
    liabilities: Optional[float] = None
    equity: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    provenance: Provenance = field(default_factory=lambda: Provenance(status="RESEARCH"))
    authority: str = DataAuthority.RESEARCH.value

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EnrichmentDecision:
    allow: bool
    outcome: str
    reason: str
    layer: str
    authority: str
    presence: str = DataPresence.NO_DATA.value
    detail: str = ""
    symbols_affected: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
