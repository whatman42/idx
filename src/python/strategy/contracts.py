"""Strategy Engine contracts — single source of truth for multi-strategy alpha.

Pipeline target:
  Market Data → DQ → Features → Regime → Multi-Strategy Alpha → ML Ensemble
  → Governor → Position Sizing → Entry/Exit → Risk → OrderIntent

No strategy enters production without PromotionGate PASS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class StrategyFamily(str, Enum):
    TREND = "TREND"
    MOMENTUM = "MOMENTUM"
    BREAKOUT = "BREAKOUT"
    MEAN_REVERSION = "MEAN_REVERSION"
    VOLUME_LIQUIDITY = "VOLUME_LIQUIDITY"
    RELATIVE_STRENGTH = "RELATIVE_STRENGTH"
    VOLATILITY_REGIME = "VOLATILITY_REGIME"
    RULE_SMA = "RULE_SMA"  # existing ops baseline


class Decision(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    NO_SIGNAL = "NO_SIGNAL"


@dataclass(frozen=True)
class StrategySpec:
    """Immutable registration of one alpha strategy."""
    strategy_id: str
    family: StrategyFamily
    display: str
    description: str
    required_features: tuple[str, ...] = ()
    compatible_regimes: tuple[str, ...] = ()  # empty = all
    default_weight: float = 1.0
    status: str = "RESEARCH"  # RESEARCH | CANDIDATE | PROMOTED | RETIRED


@dataclass
class AlphaScore:
    """Per-strategy contribution for one symbol at one timestamp."""
    strategy_id: str
    family: str
    symbol: str
    score: float  # typically [-1, +1] or [0, 1] — documented per strategy
    direction: int  # +1 long bias, -1 short bias, 0 neutral
    confidence: float = 0.0  # internal rank/strength, NOT probability of rise
    reasons: list[str] = field(default_factory=list)
    regime_compatible: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class RegimeState:
    """Market regime snapshot used by ensemble and sizing."""
    trend: str = "neutral"  # bull | bear | neutral
    volatility: str = "medium"  # low | medium | high
    drawdown: str = "normal"  # normal | elevated | stress
    liquidity: str = "normal"  # thin | normal | abundant
    momentum: str = "neutral"  # up | down | neutral
    trend_code: float = 0.0
    vol_code: float = 1.0
    stress_score: float = 0.0
    source: str = "feature_engine"
    reasons: list[str] = field(default_factory=list)

    def allows_mean_reversion(self) -> bool:
        return self.trend in ("neutral",) and self.volatility in ("low", "medium")

    def allows_breakout(self) -> bool:
        return self.volatility in ("medium", "high") and self.liquidity != "thin"

    def allows_trend(self) -> bool:
        return self.trend in ("bull", "bear") and self.drawdown != "stress"


@dataclass
class EnsembleInput:
    symbol: str
    timestamp: str
    alphas: list[AlphaScore]
    regime: RegimeState
    ml_probability: Optional[float] = None  # calibrated if available
    ml_model_id: str = ""
    data_quality_ok: bool = True
    liquidity_score: float = 1.0  # 0 thin .. 1 abundant
    risk_penalty: float = 0.0
    liquidity_penalty: float = 0.0
    dq_penalty: float = 0.0


@dataclass
class SignalDecision:
    """Governor output before sizing."""
    symbol: str
    decision: Decision
    composite_score: float
    threshold_used: float
    regime: RegimeState
    contributing_strategies: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    ml_probability: Optional[float] = None
    blocked: bool = False
    block_reason: str = ""


@dataclass
class ExitPlan:
    """Adaptive exit parameters for one position/intent."""
    sl_pct: float = 0.03
    tp_pct: float = 0.06
    atr_sl_mult: Optional[float] = None
    atr_tp_mult: Optional[float] = None
    trailing_pct: Optional[float] = None
    time_stop_bars: int = 5
    trend_break_exit: bool = True
    momentum_deterioration_exit: bool = True
    max_adverse_excursion_pct: Optional[float] = None
    method: str = "static_pct"  # static_pct | atr | hybrid


@dataclass
class SizePlan:
    """Risk-based position size before hard caps."""
    weight: float  # fraction of equity
    risk_budget_pct: float
    stop_distance_pct: float
    method: str = "risk_budget"  # fixed_weight | risk_budget
    caps_applied: list[str] = field(default_factory=list)


@dataclass
class OrderIntent:
    """Final paper/live-intent — never implies broker execution by itself."""
    symbol: str
    side: int  # +1 buy, -1 sell
    decision: Decision
    weight: float
    entry_reference: float
    exit_plan: ExitPlan
    size_plan: SizePlan
    signal_id: str
    strategy_ids: list[str] = field(default_factory=list)
    composite_score: float = 0.0
    regime_tags: list[str] = field(default_factory=list)
    live_execution: bool = False  # always False unless explicit ops enable
    meta: dict[str, Any] = field(default_factory=dict)
