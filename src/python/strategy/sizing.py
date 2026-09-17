"""Position sizing — risk budget / stop distance, then hard caps.

Industry pattern (Abu AtrPosition, Van Tharp, quant desks):
  weight = risk_budget_pct / stop_distance_pct
  then min(max_weight, liquidity, remaining exposure, regime scale).

Aligned with ops.risk_gate defaults (1% risk, 12% max weight).
"""
from __future__ import annotations

from src.python.strategy.contracts import RegimeState, SizePlan

DEFAULT_RISK_BUDGET = 0.01
DEFAULT_MAX_WEIGHT = 0.12


def compute_size(
    *,
    stop_distance_pct: float,
    risk_budget_pct: float = DEFAULT_RISK_BUDGET,
    max_weight: float = DEFAULT_MAX_WEIGHT,
    min_weight: float = 0.0,
    liquidity_cap: float = 1.0,
    portfolio_exposure: float = 0.0,
    max_portfolio_exposure: float = 0.70,
    regime: RegimeState | None = None,
    fixed_weight: float | None = None,
) -> SizePlan:
    caps: list[str] = []
    stop = max(float(stop_distance_pct), 1e-4)

    if fixed_weight is not None:
        w = float(fixed_weight)
        method = "fixed_weight"
    else:
        w = float(risk_budget_pct) / stop
        method = "risk_budget"

    if w > max_weight:
        w = max_weight
        caps.append("max_position")
    if w > liquidity_cap:
        w = liquidity_cap
        caps.append("liquidity_limit")

    remaining = max(0.0, max_portfolio_exposure - float(portfolio_exposure))
    if w > remaining:
        w = remaining
        caps.append("portfolio_exposure")

    if regime is not None:
        if regime.drawdown == "stress" or regime.stress_score >= 0.7:
            w *= 0.5
            caps.append("regime_stress_scale")
        elif regime.volatility == "high":
            w *= 0.75
            caps.append("regime_high_vol_scale")
        if regime.liquidity == "thin":
            w *= 0.6
            caps.append("regime_thin_liq_scale")

    w = max(min_weight, min(w, max_weight))
    if w <= 1e-8:
        caps.append("zero_after_caps")

    return SizePlan(
        weight=float(w),
        risk_budget_pct=float(risk_budget_pct),
        stop_distance_pct=float(stop),
        method=method,
        caps_applied=caps,
    )
