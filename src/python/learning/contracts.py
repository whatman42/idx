"""Learning-loop contracts — experience, hypothesis, experiment, evolution.

Principles:
  Bot may improvise hypotheses; must NOT improvise money, risk, SSOT, or production
  strategy without EvidencePackage + PromotionGate.

Statuses flow:
  OBSERVED → HYPOTHESIS → EXPERIMENT → VALIDATED → CANDIDATE → PROMOTED
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class LearningStatus(str, Enum):
    OBSERVED = "OBSERVED"
    HYPOTHESIS = "HYPOTHESIS"
    EXPERIMENT = "EXPERIMENT"
    VALIDATED = "VALIDATED"
    CANDIDATE = "CANDIDATE"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    RETIRED = "RETIRED"


class EpisodeOutcome(str, Enum):
    WIN = "WIN"
    LOSS = "LOSS"
    FLAT = "FLAT"
    OPEN = "OPEN"
    SKIPPED = "SKIPPED"


class EpisodeLifecycle(str, Enum):
    """Explicit lifecycle — missing exit must NOT silently become COMPLETED."""
    OPEN = "OPEN"
    COMPLETED = "COMPLETED"
    ATTRIBUTED = "ATTRIBUTED"
    INVALID = "INVALID"
    BLOCKED = "BLOCKED"


class RootCauseCandidate(str, Enum):
    FALSE_BREAKOUT = "FALSE_BREAKOUT"
    LATE_ENTRY = "LATE_ENTRY"
    BAD_REGIME = "BAD_REGIME"
    OVERSIZE = "OVERSIZE"
    TIGHT_STOP = "TIGHT_STOP"
    LOOSE_STOP = "LOOSE_STOP"
    ENSEMBLE_DISAGREE = "ENSEMBLE_DISAGREE"
    GOVERNOR_TOO_STRICT = "GOVERNOR_TOO_STRICT"
    LIQUIDITY = "LIQUIDITY"
    UNKNOWN = "UNKNOWN"
    NONE = "NONE"


class DriftKind(str, Enum):
    FEATURE = "FEATURE"
    REGIME = "REGIME"
    MODEL = "MODEL"
    PERFORMANCE = "PERFORMANCE"
    EXECUTION = "EXECUTION"


@dataclass
class SignalEpisode:
    """One closed decision path: signal → fill → exit → outcome.

    Deterministic facts only. LLM may interpret, never invent these fields.
    Phase-1: ONE fill → ONE episode via idempotency_key.
    """
    episode_id: str
    trading_date: str
    symbol: str
    strategy_id: str
    strategy_version: str = "0.0.0"
    regime: str = "unknown"
    side: int = 0
    confidence: float = 0.0
    score: float = 0.0
    ensemble_votes: dict[str, float] = field(default_factory=dict)
    feature_snapshot: dict[str, float] = field(default_factory=dict)
    risk_decision: str = "ALLOW"
    governor_decision: str = "BUY"
    entry_px: float = 0.0
    exit_px: float = 0.0
    exit_reason: str = ""
    r_multiple: float = 0.0
    pnl: float = 0.0
    outcome: str = EpisodeOutcome.OPEN.value
    signal_id: str = ""
    fill_id: str = ""
    entry_trade_id: str = ""
    idempotency_key: str = ""
    lifecycle: str = EpisodeLifecycle.OPEN.value
    qty: float = 0.0
    cost_basis: float = 0.0
    fees: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Hypothesis:
    hypothesis_id: str
    statement: str
    regimes: list[str] = field(default_factory=list)
    strategies: list[str] = field(default_factory=list)
    counter_hypothesis: str = ""
    status: str = LearningStatus.HYPOTHESIS.value
    evidence_count: int = 0
    experiment_ids: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CounterfactualScenario:
    name: str
    description: str
    hypothetical_r: float
    delta_r: float
    category: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CounterfactualReport:
    episode_id: str
    actual_r: float
    scenarios: list[CounterfactualScenario] = field(default_factory=list)
    dominant_category: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "actual_r": self.actual_r,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "dominant_category": self.dominant_category,
        }


@dataclass
class ExperimentSpec:
    experiment_id: str
    hypothesis_id: str
    name: str
    baseline_id: str = "rule_sma20@1.0"
    challenger_strategy_id: str = ""
    challenger_version: str = "0.0.0"
    dataset_hash: str = ""
    feature_hash: str = ""
    cost_model: str = "simulation_v2"
    parameters: dict[str, Any] = field(default_factory=dict)
    status: str = LearningStatus.EXPERIMENT.value
    metrics: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MetaDecision:
    """Meta-learner output — reliability/uncertainty, not a BUY probability."""
    symbol: str
    expected_edge: float = 0.0
    uncertainty: float = 1.0
    strategy_reliability: dict[str, float] = field(default_factory=dict)
    regime_compatibility: float = 0.5
    decision_quality: float = 0.0
    recommended_action: str = "HOLD"
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class HealthReport:
    data_health: str = "OK"
    feature_health: str = "OK"
    model_health: str = "OK"
    strategy_health: str = "OK"
    regime_health: str = "OK"
    execution_health: str = "OK"
    learning_health: str = "OK"
    decision_confidence: str = "OK"
    warnings: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DriftAlert:
    kind: str
    name: str
    score: float
    threshold: float
    status: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IntegrityResult:
    """Learning data integrity check — Ledger remains SSOT."""
    ok: bool
    ledger_pnl: float = 0.0
    episode_pnl: float = 0.0
    attribution_pnl: float = 0.0
    delta_ledger_episode: float = 0.0
    delta_episode_attribution: float = 0.0
    issues: list[str] = field(default_factory=list)
    learning_data_integrity: str = "PASS"
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
