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


class FailureType(str, Enum):
    """Controlled vocabulary — deterministic classification only."""
    STOP_LOSS = "STOP_LOSS"
    TAKE_PROFIT_MISSED = "TAKE_PROFIT_MISSED"
    LOW_EDGE = "LOW_EDGE"
    REGIME_MISMATCH = "REGIME_MISMATCH"
    TIMING_FAILURE = "TIMING_FAILURE"
    VOLATILITY_SPIKE = "VOLATILITY_SPIKE"
    FALSE_SIGNAL = "FALSE_SIGNAL"
    EXECUTION_DEVIATION = "EXECUTION_DEVIATION"
    DATA_ANOMALY = "DATA_ANOMALY"
    ABNORMAL_LOSS = "ABNORMAL_LOSS"
    UNKNOWN = "UNKNOWN"
    NONE = "NONE"  # not a system failure


class DriftState(str, Enum):
    """Canonical drift states. OK/WARN map to NORMAL/WATCH for compat."""
    NORMAL = "NORMAL"
    WATCH = "WATCH"
    DEGRADED = "DEGRADED"
    BLOCKED = "BLOCKED"
    # legacy aliases used by existing tests
    OK = "OK"
    WARN = "WARN"


class CounterfactualAction(str, Enum):
    HOLD = "HOLD"
    NO_TRADE = "NO_TRADE"
    ALT_STRATEGY = "ALT_STRATEGY"
    ENTRY_DELAY_1_BAR = "ENTRY_DELAY_1_BAR"
    EXIT_EARLIER = "EXIT_EARLIER"
    EXIT_LATER = "EXIT_LATER"
    TIGHTER_SL = "TIGHTER_SL"
    WIDER_SL = "WIDER_SL"
    REGIME_BLOCK = "REGIME_BLOCK"
