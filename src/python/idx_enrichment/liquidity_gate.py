"""Liquidity Gate — optional unless policy.liquidity_required."""
from __future__ import annotations

from typing import Optional

from src.python.idx_enrichment.models import (
    DataAuthority,
    DataPresence,
    EnrichmentDecision,
    GateOutcome,
    LiquiditySnapshot,
)
from src.python.idx_enrichment.policy import DEFAULT_POLICY, EnrichmentPolicy, resolve_presence

MIN_AVG_VALUE_RP = 50_000_000.0
MIN_AVG_VOLUME = 100_000.0
MIN_TRADING_DAYS = 5


def evaluate_liquidity(
    symbol: str,
    snap: Optional[LiquiditySnapshot],
    *,
    trading_date: str = "",
    policy: Optional[EnrichmentPolicy] = None,
    min_avg_value: float = MIN_AVG_VALUE_RP,
    min_avg_volume: float = MIN_AVG_VOLUME,
    min_trading_days: int = MIN_TRADING_DAYS,
) -> EnrichmentDecision:
    pol = policy or DEFAULT_POLICY
    sym = str(symbol).upper().strip()

    if snap is None or (snap.avg_value <= 0 and snap.avg_volume <= 0 and snap.trading_days <= 0):
        presence = DataPresence.NO_DATA
        if pol.liquidity_required:
            return EnrichmentDecision(
                allow=False,
                outcome=GateOutcome.BLOCK.value,
                reason="LIQUIDITY_NO_DATA_REQUIRED",
                layer="liquidity",
                authority=DataAuthority.RISK_GATE.value,
                presence=presence.value,
                detail="liquidity required but no snapshot",
                symbols_affected=[sym],
            )
        return EnrichmentDecision(
            allow=True,
            outcome=GateOutcome.PASS.value,
            reason="LIQUIDITY_NO_DATA_OPTIONAL",
            layer="liquidity",
            authority=DataAuthority.RISK_GATE.value,
            presence=presence.value,
            detail="liquidity optional — continue",
            symbols_affected=[sym],
        )

    as_of = snap.as_of or getattr(snap.provenance, "as_of", "") or ""
    presence = resolve_presence(
        has_record=True, as_of=as_of, trading_date=trading_date, max_stale_days=pol.max_stale_days
    )
    if presence == DataPresence.INVALID:
        return EnrichmentDecision(
            allow=False,
            outcome=GateOutcome.BLOCK.value,
            reason="LIQUIDITY_INVALID",
            layer="liquidity",
            authority=DataAuthority.RISK_GATE.value,
            presence=presence.value,
            detail="invalid liquidity record",
            symbols_affected=[sym],
        )
    if presence == DataPresence.STALE and pol.liquidity_on_stale == "BLOCK":
        return EnrichmentDecision(
            allow=False,
            outcome=GateOutcome.BLOCK.value,
            reason="LIQUIDITY_STALE",
            layer="liquidity",
            authority=DataAuthority.RISK_GATE.value,
            presence=presence.value,
            detail=f"stale as_of={as_of}",
            symbols_affected=[sym],
        )

    fails: list[str] = []
    if snap.avg_value > 0 and snap.avg_value < min_avg_value:
        fails.append(f"avg_value={snap.avg_value:.0f}<{min_avg_value:.0f}")
    if snap.avg_volume > 0 and snap.avg_volume < min_avg_volume:
        fails.append(f"avg_volume={snap.avg_volume:.0f}<{min_avg_volume:.0f}")
    if snap.trading_days > 0 and snap.trading_days < min_trading_days:
        fails.append(f"trading_days={snap.trading_days}<{min_trading_days}")
    if fails:
        return EnrichmentDecision(
            allow=False,
            outcome=GateOutcome.BLOCK.value,
            reason="SKIPPED_LIQUIDITY",
            layer="liquidity",
            authority=DataAuthority.RISK_GATE.value,
            presence=DataPresence.DATA_PRESENT.value,
            detail="; ".join(fails),
            symbols_affected=[sym],
        )
    return EnrichmentDecision(
        allow=True,
        outcome=GateOutcome.PASS.value,
        reason="LIQUIDITY_PASS",
        layer="liquidity",
        authority=DataAuthority.RISK_GATE.value,
        presence=DataPresence.DATA_PRESENT.value,
        detail="within thresholds",
        symbols_affected=[sym],
    )
