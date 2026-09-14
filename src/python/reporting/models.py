"""Canonical structured reports — single source of truth for Telegram numbers.

Telegram composers MUST NOT recompute financial fields; they only render these models.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class OpenPositionView:
    symbol: str
    entry_price: float
    mark_price: float
    shares: float
    lots: float
    market_value: float
    unrealized_pnl: float
    tp1: float = 0.0
    tp2: float = 0.0
    stop_loss: float = 0.0
    opened_at: str = ""
    duration: str = "Not configured"
    signal_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExitReport:
    symbol: str
    entry_price: float
    exit_price: float
    shares: float
    lots: float
    realized_pnl: float
    pnl_pct: float
    duration: str
    exit_reason: str
    timestamp: str
    signal_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SignalReport:
    signal_id: str
    timestamp: str
    symbol: str
    decision: str  # BUY | SELL | NO_SIGNAL
    timeframe: str = "Swing 5–20 hari"
    market_regime: str = "Unknown"
    entry_reference: float = 0.0
    entry_low: float = 0.0
    entry_high: float = 0.0
    stop_loss: float = 0.0
    tp1: float = 0.0
    tp2: float = 0.0
    shares: float = 0.0
    lots: float = 0.0
    position_value: float = 0.0
    allocation_pct: float = 0.0
    risk_amount: float = 0.0
    risk_pct: float = 0.0
    rr_tp1: Optional[float] = None
    rr_tp2: Optional[float] = None
    confidence: float = 0.0  # 0–100 scale (model score, not calibrated probability)
    confidence_method: str = "model_score_unspecified"
    risk_score: float = 0.0
    expected_value: Optional[float] = None
    technical_factors: list[str] = field(default_factory=list)
    volume_factor: str = "Data tidak tersedia"
    trend_factor: str = "Data tidak tersedia"
    momentum_factor: str = "Data tidak tersedia"
    liquidity_factor: str = "Data tidak tersedia"
    model_agreement: str = "Data tidak tersedia"
    explanation_context: list[str] = field(default_factory=list)
    model_version: str = ""
    feature_version: str = ""
    management: list[str] = field(default_factory=lambda: ["Not configured"])
    fill_status: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PortfolioSnapshot:
    equity: float
    cash: float
    market_value: float
    exposure_pct: float
    realized_pnl: float
    unrealized_pnl: float
    open_positions: list[OpenPositionView] = field(default_factory=list)
    initial_capital: float = 0.0
    simulation_session_id: str = ""
    last_event: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class CycleReport:
    """Full cycle payload: one optional top signal + portfolio + exits + meta."""
    trading_date: str
    mode: str
    signal_only: bool = True
    live_execution: bool = False
    signal: Optional[SignalReport] = None
    portfolio: Optional[PortfolioSnapshot] = None
    exits: list[ExitReport] = field(default_factory=list)
    status: str = "SUCCESS"
    governor_action: str = ""
    dq_status: str = ""
    data_source: str = ""
    integrity_ok: bool = True
    integrity_errors: list[str] = field(default_factory=list)
    model_version: str = ""
    no_signal_reasons: list[str] = field(default_factory=list)
    risk_gate: str = "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "trading_date": self.trading_date,
            "mode": self.mode,
            "signal_only": self.signal_only,
            "live_execution": self.live_execution,
            "signal": self.signal.to_dict() if self.signal else None,
            "portfolio": self.portfolio.to_dict() if self.portfolio else None,
            "exits": [e.to_dict() for e in self.exits],
            "status": self.status,
            "governor_action": self.governor_action,
            "dq_status": self.dq_status,
            "data_source": self.data_source,
            "integrity_ok": self.integrity_ok,
            "integrity_errors": list(self.integrity_errors),
            "model_version": self.model_version,
            "no_signal_reasons": list(self.no_signal_reasons),
            "risk_gate": self.risk_gate,
        }
