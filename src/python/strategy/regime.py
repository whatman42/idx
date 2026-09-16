"""Regime detection — maps feature/market context into RegimeState for ensemble."""
from __future__ import annotations

from typing import Any, Optional

from src.python.strategy.contracts import RegimeState


def _label_trend(code: float) -> str:
    if code > 0.25:
        return "bull"
    if code < -0.25:
        return "bear"
    return "neutral"


def _label_vol(code: float) -> str:
    if code >= 2.0:
        return "high"
    if code <= 0.5:
        return "low"
    return "medium"


def _label_dd(code: float) -> str:
    if code >= 0.15:
        return "stress"
    if code >= 0.08:
        return "elevated"
    return "normal"


def _label_liq(code: float) -> str:
    if code < 0.35:
        return "thin"
    if code > 0.75:
        return "abundant"
    return "normal"


def _label_mom(code: float) -> str:
    if code > 0.15:
        return "up"
    if code < -0.15:
        return "down"
    return "neutral"


class RegimeEngine:
    """Deterministic regime labels from numeric feature codes / market context."""

    def detect(
        self,
        *,
        trend_code: float = 0.0,
        vol_code: float = 1.0,
        drawdown: float = 0.0,
        liquidity_score: float = 0.5,
        momentum_code: float = 0.0,
        stress_score: float = 0.0,
        source: str = "feature_engine",
        extra: Optional[dict[str, Any]] = None,
    ) -> RegimeState:
        reasons: list[str] = []
        trend = _label_trend(float(trend_code))
        vol = _label_vol(float(vol_code))
        dd = _label_dd(float(drawdown))
        liq = _label_liq(float(liquidity_score))
        mom = _label_mom(float(momentum_code))
        if stress_score >= 0.7 or dd == "stress":
            reasons.append("market_stress")
        if vol == "high":
            reasons.append("high_volatility")
        if liq == "thin":
            reasons.append("thin_liquidity")
        if extra:
            for k, v in list(extra.items())[:8]:
                reasons.append(f"{k}={v}")
        return RegimeState(
            trend=trend,
            volatility=vol,
            drawdown=dd,
            liquidity=liq,
            momentum=mom,
            trend_code=float(trend_code),
            vol_code=float(vol_code),
            stress_score=float(stress_score),
            source=source,
            reasons=reasons,
        )

    def from_feature_row(self, row: dict[str, Any]) -> RegimeState:
        """Build regime from a feature dict (keys optional; safe defaults)."""
        return self.detect(
            trend_code=float(row.get("regime_trend") or row.get("ihsg_trend_regime") or 0.0),
            vol_code=float(row.get("regime_vol") or row.get("mkt_vol_regime") or 1.0),
            drawdown=abs(float(row.get("regime_dd") or row.get("ihsg_dd_60") or 0.0)),
            liquidity_score=float(row.get("regime_liquidity") or 0.5),
            momentum_code=float(row.get("regime_momentum") or row.get("mom_10_21") or 0.0),
            stress_score=float(row.get("mkt_stress") or 0.0),
            source="feature_row",
        )
