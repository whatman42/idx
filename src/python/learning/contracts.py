"""Learning-loop contracts — experience, hypothesis, experiment, evolution.

Principles:
  Bot may improvise hypotheses; must NOT improvise money, risk, SSOT, or production
  strategy without EvidencePackage + PromotionGate.

Statuses flow:
  OBSERVED → HYPOTHESIS → EXPERIMENT → VALIDATED → CANDIDATE → PROMOTED

This module is the single import surface:
  from src.python.learning.contracts import SignalEpisode, AttributionReport, ...
Enums live in contracts_enums; core episode types in contracts_types_a1/a2.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# ---- Enums (canonical definitions also mirrored in contracts_enums) ----
from src.python.learning.contracts_enums import (  # noqa: F401
    CounterfactualAction,
    DriftKind,
    DriftState,
    EpisodeLifecycle,
    EpisodeOutcome,
    FailureType,
    LearningStatus,
    RootCauseCandidate,
)

# ---- Core experience records ----
from src.python.learning.contracts_types_a1 import SignalEpisode  # noqa: F401
from src.python.learning.contracts_types_a2 import (  # noqa: F401
    AttributionReport,
    FailureRecord,
)


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
    """Ledger vs Episode vs Attribution P&L reconciliation."""
    ok: bool
    ledger_pnl: float = 0.0
    episode_pnl: float = 0.0
    attribution_pnl: float = 0.0
    delta_ledger_episode: float = 0.0
    delta_episode_attribution: float = 0.0
    issues: list[str] = field(default_factory=list)
    learning_data_integrity: str = "PASS"  # PASS | FAIL
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


__all__ = [
    "LearningStatus",
    "EpisodeOutcome",
    "EpisodeLifecycle",
    "RootCauseCandidate",
    "DriftKind",
    "FailureType",
    "DriftState",
    "CounterfactualAction",
    "SignalEpisode",
    "AttributionReport",
    "FailureRecord",
    "Hypothesis",
    "CounterfactualScenario",
    "CounterfactualReport",
    "ExperimentSpec",
    "MetaDecision",
    "HealthReport",
    "DriftAlert",
    "IntegrityResult",
]
