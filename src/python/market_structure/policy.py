"""Policy A baseline: only CONTINUOUS may pass; FCA/HALTED/SUSPENDED/UNKNOWN → BLOCK."""
from __future__ import annotations

from src.python.market_structure.freshness import is_stale
from src.python.market_structure.models import (
    BlockReason,
    MarketStructure,
    MarketStructureSnapshot,
    StructureGateResult,
)

POLICY_NAME = "FCA_BLOCK"


def evaluate_structure(
    snapshot: MarketStructureSnapshot | None,
    *,
    max_age_seconds: float = 86_400.0,
    now=None,
) -> StructureGateResult:
    if snapshot is None:
        return StructureGateResult(
            allow=False,
            reason=BlockReason.MISSING_SNAPSHOT,
            symbol="",
            market_mode=MarketStructure.UNKNOWN.value,
            detected_at="",
            source="",
            detail="no MarketStructureSnapshot",
            policy=POLICY_NAME,
        )

    mode = snapshot.structure
    if isinstance(mode, str):
        try:
            mode = MarketStructure(mode)
        except ValueError:
            mode = MarketStructure.UNKNOWN

    base = dict(
        symbol=snapshot.symbol,
        market_mode=mode.value,
        detected_at=snapshot.as_of,
        source=snapshot.source,
        policy=POLICY_NAME,
    )

    if is_stale(snapshot, now=now, max_age_seconds=max_age_seconds):
        return StructureGateResult(allow=False, reason=BlockReason.MARKET_DATA_STALE, detail="stale metadata", **base)

    if mode == MarketStructure.CONTINUOUS:
        return StructureGateResult(allow=True, reason=BlockReason.NONE, detail="continuous ok", **base)
    if mode == MarketStructure.FCA:
        return StructureGateResult(allow=False, reason=BlockReason.FCA_INSTRUMENT, detail="Policy A FCA block", **base)
    if mode == MarketStructure.HALTED:
        return StructureGateResult(allow=False, reason=BlockReason.HALTED, detail="halted", **base)
    if mode == MarketStructure.SUSPENDED:
        return StructureGateResult(allow=False, reason=BlockReason.SUSPENDED, detail="suspended", **base)
    return StructureGateResult(
        allow=False,
        reason=BlockReason.MARKET_STRUCTURE_UNKNOWN,
        detail="UNKNOWN is not CONTINUOUS",
        **base,
    )
