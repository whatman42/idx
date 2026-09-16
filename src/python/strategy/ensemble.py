"""Ensemble Governor — not simple majority vote.

Composite =
  Σ (strategy_score × weight × regime_gate)
  + ML term (if calibrated)
  − risk_penalty − liquidity_penalty − dq_penalty

Thresholds adapt by regime. Safety blocks override scores.
"""
from __future__ import annotations

from typing import Optional

from src.python.strategy.contracts import (
    Decision,
    EnsembleInput,
    RegimeState,
    SignalDecision,
)
from src.python.strategy.registry import STRATEGY_REGISTRY


def _regime_threshold(regime: RegimeState) -> float:
    """Higher bar in stress / high vol / thin liquidity."""
    base = 0.35
    if regime.drawdown == "stress" or regime.stress_score >= 0.7:
        base = 0.55
    elif regime.volatility == "high":
        base = 0.45
    elif regime.liquidity == "thin":
        base = 0.50
    elif regime.trend == "bull" and regime.volatility == "low":
        base = 0.28
    return base


def _family_regime_gate(family: str, regime: RegimeState) -> float:
    """0 = fully gated off, 1 = full weight."""
    f = family.upper()
    if f == "MEAN_REVERSION":
        return 1.0 if regime.allows_mean_reversion() else 0.15
    if f == "BREAKOUT":
        return 1.0 if regime.allows_breakout() else 0.25
    if f == "TREND":
        return 1.0 if regime.allows_trend() else 0.40
    if regime.drawdown == "stress":
        return 0.35
    return 1.0


class EnsembleGovernor:
    """Combine multi-strategy alphas into a single SignalDecision."""

    def __init__(self, *, ml_weight: float = 0.25, min_contributors: int = 1):
        self.ml_weight = float(ml_weight)
        self.min_contributors = int(min_contributors)

    def decide(self, inp: EnsembleInput) -> SignalDecision:
        if not inp.data_quality_ok:
            return SignalDecision(
                symbol=inp.symbol,
                decision=Decision.NO_SIGNAL,
                composite_score=0.0,
                threshold_used=_regime_threshold(inp.regime),
                regime=inp.regime,
                reasons=["data_quality_block"],
                blocked=True,
                block_reason="dq_fail",
                ml_probability=inp.ml_probability,
            )

        threshold = _regime_threshold(inp.regime)
        weighted = 0.0
        weight_sum = 0.0
        contributors: list[str] = []
        reasons: list[str] = []

        for a in inp.alphas:
            if not a.regime_compatible:
                reasons.append(f"{a.strategy_id}:regime_incompatible")
                continue
            spec = STRATEGY_REGISTRY.get(a.strategy_id)
            base_w = float(spec.default_weight) if spec else 1.0
            gate = _family_regime_gate(a.family, inp.regime)
            w = base_w * gate
            if w <= 1e-9:
                continue
            # score expected roughly in [-1, 1]; direction reinforces sign
            s = float(a.score) * (1.0 if a.direction >= 0 else -1.0)
            weighted += s * w
            weight_sum += w
            contributors.append(a.strategy_id)
            if a.reasons:
                reasons.extend(a.reasons[:2])

        if weight_sum > 1e-9:
            composite = weighted / weight_sum
        else:
            composite = 0.0
            reasons.append("no_active_alpha")

        if inp.ml_probability is not None:
            # map probability to [-1, 1] around 0.5; do not treat as calibrated certainty unless marked
            ml_term = (float(inp.ml_probability) - 0.5) * 2.0
            composite = (1.0 - self.ml_weight) * composite + self.ml_weight * ml_term
            reasons.append(f"ml_term={ml_term:.3f}")

        composite -= float(inp.risk_penalty) + float(inp.liquidity_penalty) + float(inp.dq_penalty)
        if inp.risk_penalty:
            reasons.append(f"risk_penalty={inp.risk_penalty:.3f}")
        if inp.liquidity_penalty:
            reasons.append(f"liq_penalty={inp.liquidity_penalty:.3f}")

        decision = Decision.NO_SIGNAL
        if len(contributors) < self.min_contributors and inp.ml_probability is None:
            decision = Decision.NO_SIGNAL
            reasons.append("insufficient_contributors")
        elif composite >= threshold:
            decision = Decision.BUY
        elif composite <= -threshold:
            decision = Decision.SELL
        elif abs(composite) >= threshold * 0.5:
            decision = Decision.HOLD
        else:
            decision = Decision.NO_SIGNAL

        return SignalDecision(
            symbol=inp.symbol,
            decision=decision,
            composite_score=float(composite),
            threshold_used=float(threshold),
            regime=inp.regime,
            contributing_strategies=contributors,
            reasons=reasons[:12],
            ml_probability=inp.ml_probability,
            blocked=False,
            block_reason="",
        )
