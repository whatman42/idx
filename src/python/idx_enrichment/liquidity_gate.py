"""Liquidity Gate — risk constraint before paper entry sizing assumptions hold."""
from __future__ import annotations

from typing import Optional

from src.python.idx_enrichment.models import DataAuthority, EnrichmentDecision, LiquiditySnapshot

MIN_AVG_VALUE_RP = 50_000_000.0
MIN_AVG_VOLUME = 100_000.0
MIN_TRADING_DAYS = 5


def evaluate_liquidity(
    symbol: str,
    snap: Optional[LiquiditySnapshot],
    *,
    min_avg_value: float = MIN_AVG_VALUE_RP,
    min_avg_volume: float = MIN_AVG_VOLUME,
    min_trading_days: int = MIN_TRADING_DAYS,
) -> EnrichmentDecision:
    sym = str(symbol).upper().strip()
    if snap is None:
        return EnrichmentDecision(
            allow=True,
            reason="NO_LIQ_DATA",
            layer="liquidity",
            authority=DataAuthority.RISK_GATE.value,
            detail="no liquidity snapshot — pass (not fail-closed until feed certified)",
            symbols_affected=[sym],
        )
    fails: list[str] = []
    if snap.avg_value > 0 and snap.avg_value < min_avg_value:
        fails.append(f"avg_value={snap.avg_value:.0f}<{min_avg_value:.0f}")
    if snap.avg_volume > 0 and snap.avg_volume < min_avg_volume:
        fails.append(f"avg_volume={snap.avg_volume:.0f}<{min_avg_volume:.0f}")
    if snap.trading_days > 0 and snap.trading_days < min_trading_days:
        fails.append(f"trading_days={snap.trading_days}<{min_trading_days}")
    if snap.avg_value <= 0 and snap.avg_volume <= 0 and snap.trading_days <= 0:
        return EnrichmentDecision(
            allow=True,
            reason="NO_LIQ_DATA",
            layer="liquidity",
            authority=DataAuthority.RISK_GATE.value,
            detail="empty liquidity metrics",
            symbols_affected=[sym],
        )
    if fails:
        return EnrichmentDecision(
            allow=False,
            reason="SKIPPED_LIQUIDITY",
            layer="liquidity",
            authority=DataAuthority.RISK_GATE.value,
            detail="; ".join(fails),
            symbols_affected=[sym],
        )
    return EnrichmentDecision(
        allow=True,
        reason="PASS",
        layer="liquidity",
        authority=DataAuthority.RISK_GATE.value,
        detail="liquidity within thresholds",
        symbols_affected=[sym],
    )
