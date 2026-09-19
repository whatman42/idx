"""Learning-loop dataclasses — experience records (part)."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from src.python.learning.contracts_enums import LearningStatus, EpisodeOutcome, EpisodeLifecycle

@dataclass
class AttributionReport:
    episode_id: str
    symbol: str
    outcome: str
    r_multiple: float
    primary_strategy: str
    regime: str
    contributing_strategies: list[str] = field(default_factory=list)
    feature_highlights: dict[str, float] = field(default_factory=dict)
    root_cause_candidates: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    pnl: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class FailureRecord:
    failure_id: str
    episode_id: str
    regime: str
    strategy_id: str
    signal: str
    r_multiple: float
    root_cause: str
    similar_count: int = 0
    historical_failure_rate: float = 0.0
    pattern: str = ""
    status: str = LearningStatus.OBSERVED.value
    proposed_action: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    # Phase-2 structured fields (optional; also mirrored in meta)
    failure_type: str = "UNKNOWN"
    severity: str = "LOW"
    confidence: float = 0.0
    symbol: str = ""
    strategy_version: str = ""
    model_version: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    pnl: float = 0.0
    holding_period: float = 0.0
    feature_snapshot_id: str = ""
    attribution_id: str = ""
    description: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    idempotency_key: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
