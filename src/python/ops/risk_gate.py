"""Institutional portfolio risk gates for paper ops.

References (industry / open-source patterns):
  - 1–2% risk per trade (Van Tharp / standard discretionary quant)
  - Portfolio heat ≤ ~6% of equity at risk (HATS / prop risk desks)
  - Drawdown circuit: warn 15% / halt new entries 20% (paper-trader pattern)
  - Max concurrent positions + daily new-entry cap (quant-trade style)
  - ATR-based stop distance drives size = risk_budget / stop_pct (Abu AtrPosition)

NO broker execution. Gates only affect paper entry permission + weight.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# --- Tunables (single source) ---
RISK_PER_TRADE = 0.01          # 1% equity risked to SL
MAX_WEIGHT = 0.12              # hard cap per name
MIN_WEIGHT = 0.01
MAX_PORTFOLIO_EXPOSURE = 0.70  # sum of position weights
MAX_OPEN_POSITIONS = 8
MAX_NEW_ENTRIES_PER_DAY = 2
MAX_PORTFOLIO_HEAT = 0.06      # sum of (weight * sl_pct) open risk
DD_WARN = 0.15
DD_HALT_NEW = 0.20
DD_FORCE_REDUCE = 0.25         # informational only for paper; exits still via TP/SL


@dataclass
class RiskGateDecision:
    allow_entry: bool
    weight: float
    reason: str
    risk_budget_pct: float = RISK_PER_TRADE
    stop_distance_pct: float = 0.0
    portfolio_heat: float = 0.0
    open_count: int = 0
    drawdown: float = 0.0
    caps: list = field(default_factory=list)
    method: str = "risk_budget_atr"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def risk_defaults() -> dict[str, Any]:
    return {
        "risk_per_trade": RISK_PER_TRADE,
        "max_weight": MAX_WEIGHT,
        "min_weight": MIN_WEIGHT,
        "max_portfolio_exposure": MAX_PORTFOLIO_EXPOSURE,
        "max_open_positions": MAX_OPEN_POSITIONS,
        "max_new_entries_per_day": MAX_NEW_ENTRIES_PER_DAY,
        "max_portfolio_heat": MAX_PORTFOLIO_HEAT,
        "dd_warn": DD_WARN,
        "dd_halt_new": DD_HALT_NEW,
        "version": "risk_gate_v1",
    }


def estimate_open_heat(
    positions: dict,
    *,
    equity: float,
) -> float:
    """Sum (cost_basis/equity * sl_distance_pct) approximation for open risk."""
    if equity <= 0:
        return 0.0
    heat = 0.0
    for _sym, p in (positions or {}).items():
        if isinstance(p, dict):
            qty = float(p.get("qty") or 0)
            avg = float(p.get("avg_entry") or 0)
            sl = float(p.get("sl") or 0)
            if qty <= 0 or avg <= 0:
                continue
            cb = qty * avg
            w = cb / equity
            sl_pct = max(0.0, (avg - sl) / avg) if sl > 0 and sl < avg else 0.03
            heat += w * sl_pct
        else:
            qty = float(getattr(p, "qty", 0) or 0)
            avg = float(getattr(p, "avg_entry", 0) or 0)
            sl = float(getattr(p, "sl", 0) or 0)
            if qty <= 0 or avg <= 0:
                continue
            cb = qty * avg
            w = cb / equity
            sl_pct = max(0.0, (avg - sl) / avg) if sl > 0 and sl < avg else 0.03
            heat += w * sl_pct
    return float(heat)


def gate_new_entry(
    *,
    equity: float,
    cash: float,
    open_positions: dict,
    current_drawdown: float,
    stop_distance_pct: float,
    portfolio_exposure: float = 0.0,
    new_entries_today: int = 0,
    risk_per_trade: float = RISK_PER_TRADE,
    max_weight: float = MAX_WEIGHT,
) -> RiskGateDecision:
    """Fail-closed entry gate + risk-budget weight.

    weight ≈ risk_per_trade / stop_distance_pct, then hard caps.
    """
    caps: list[str] = []
    open_count = len([
        1 for p in (open_positions or {}).values()
        if (isinstance(p, dict) and float(p.get("qty") or 0) > 0)
        or (not isinstance(p, dict) and float(getattr(p, "qty", 0) or 0) > 0)
    ])
    heat = estimate_open_heat(open_positions, equity=equity)
    stop = max(float(stop_distance_pct or 0), 1e-4)

    if current_drawdown >= DD_HALT_NEW:
        return RiskGateDecision(
            allow_entry=False, weight=0.0, reason="HALT_DRAWDOWN",
            stop_distance_pct=stop, portfolio_heat=heat, open_count=open_count,
            drawdown=float(current_drawdown), caps=["dd_halt_new"],
        )
    if open_count >= MAX_OPEN_POSITIONS:
        return RiskGateDecision(
            allow_entry=False, weight=0.0, reason="MAX_OPEN_POSITIONS",
            stop_distance_pct=stop, portfolio_heat=heat, open_count=open_count,
            drawdown=float(current_drawdown), caps=["max_open"],
        )
    if new_entries_today >= MAX_NEW_ENTRIES_PER_DAY:
        return RiskGateDecision(
            allow_entry=False, weight=0.0, reason="MAX_NEW_ENTRIES_TODAY",
            stop_distance_pct=stop, portfolio_heat=heat, open_count=open_count,
            drawdown=float(current_drawdown), caps=["max_new_day"],
        )
    if heat >= MAX_PORTFOLIO_HEAT:
        return RiskGateDecision(
            allow_entry=False, weight=0.0, reason="PORTFOLIO_HEAT_FULL",
            stop_distance_pct=stop, portfolio_heat=heat, open_count=open_count,
            drawdown=float(current_drawdown), caps=["heat_full"],
        )
    if portfolio_exposure >= MAX_PORTFOLIO_EXPOSURE:
        return RiskGateDecision(
            allow_entry=False, weight=0.0, reason="EXPOSURE_FULL",
            stop_distance_pct=stop, portfolio_heat=heat, open_count=open_count,
            drawdown=float(current_drawdown), caps=["exposure_full"],
        )
    if cash <= 0 or equity <= 0:
        return RiskGateDecision(
            allow_entry=False, weight=0.0, reason="NO_CASH",
            stop_distance_pct=stop, portfolio_heat=heat, open_count=open_count,
            drawdown=float(current_drawdown), caps=["no_cash"],
        )

    w = float(risk_per_trade) / stop
    method = "risk_budget_atr"
    if w > max_weight:
        w = max_weight
        caps.append("max_weight")
    remaining_exp = max(0.0, MAX_PORTFOLIO_EXPOSURE - float(portfolio_exposure))
    if w > remaining_exp:
        w = remaining_exp
        caps.append("exposure_remaining")
    remaining_heat = max(0.0, MAX_PORTFOLIO_HEAT - heat)
    if stop > 0 and (w * stop) > remaining_heat and remaining_heat > 0:
        w = remaining_heat / stop
        caps.append("heat_remaining")
    if current_drawdown >= DD_WARN:
        w *= 0.5
        caps.append("dd_warn_half_size")
    w = max(0.0, min(w, max_weight))
    if w < MIN_WEIGHT:
        return RiskGateDecision(
            allow_entry=False, weight=0.0, reason="SIZE_TOO_SMALL",
            stop_distance_pct=stop, portfolio_heat=heat, open_count=open_count,
            drawdown=float(current_drawdown), caps=caps + ["below_min_weight"],
            method=method,
        )
    reason = "ALLOW"
    if "dd_warn_half_size" in caps:
        reason = "ALLOW_REDUCED_DD_WARN"
    return RiskGateDecision(
        allow_entry=True,
        weight=float(w),
        reason=reason,
        risk_budget_pct=float(risk_per_trade),
        stop_distance_pct=stop,
        portfolio_heat=heat,
        open_count=open_count,
        drawdown=float(current_drawdown),
        caps=caps,
        method=method,
    )
