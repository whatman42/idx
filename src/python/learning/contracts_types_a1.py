"""Learning-loop dataclasses — experience records (part)."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from src.python.learning.contracts_enums import LearningStatus, EpisodeOutcome, EpisodeLifecycle

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
