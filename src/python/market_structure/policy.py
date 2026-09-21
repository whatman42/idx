"""Market structure + session + eligibility policy (Policy A baseline)."""
from __future__ import annotations

from src.python.market_structure.freshness import is_stale
from src.python.market_structure.models import (
    BlockReason,
    InstrumentEligibility,
    MarketStructure,
    MarketStructureSnapshot,
    StructureGateResult,
    TradingSession,
)

POLICY_NAME = "MARKET_STRUCTURE_SAFETY"
ALLOWED_SESSIONS = frozenset({TradingSession.OPEN})


def _as_enum(val, enum_cls, default):
    if isinstance(val, enum_cls):
        return val
    try:
        return enum_cls(str(val).upper())
    except Exception:
        return default


def evaluate_structure(
    snapshot: MarketStructureSnapshot | None,
    *,
    max_age_seconds: float = 86_400.0,
    now=None,
    require_open_session: bool = True,
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

    mode = _as_enum(snapshot.structure, MarketStructure, MarketStructure.UNKNOWN)
    session = _as_enum(snapshot.session, TradingSession, TradingSession.UNKNOWN)
    elig = _as_enum(snapshot.eligibility, InstrumentEligibility, InstrumentEligibility.UNKNOWN)

    base = dict(
        symbol=snapshot.symbol,
        market_mode=mode.value,
        detected_at=snapshot.as_of,
        source=snapshot.source,
        policy=POLICY_NAME,
        session=session.value,
        eligibility=elig.value,
    )

    if is_stale(snapshot, now=now, max_age_seconds=max_age_seconds):
        return StructureGateResult(allow=False, reason=BlockReason.MARKET_DATA_STALE, detail="stale metadata", **base)

    if elig == InstrumentEligibility.DELISTED:
        return StructureGateResult(allow=False, reason=BlockReason.DELISTED, detail="delisted", **base)
    if elig == InstrumentEligibility.SUSPENDED:
        return StructureGateResult(allow=False, reason=BlockReason.SUSPENDED, detail="eligibility suspended", **base)
    if elig == InstrumentEligibility.HALTED:
        return StructureGateResult(allow=False, reason=BlockReason.TRADING_HALT, detail="eligibility halted", **base)
    if elig == InstrumentEligibility.FCA:
        return StructureGateResult(allow=False, reason=BlockReason.FCA_INSTRUMENT, detail="eligibility FCA", **base)
    if elig == InstrumentEligibility.UNKNOWN:
        return StructureGateResult(
            allow=False, reason=BlockReason.MARKET_STATUS_UNAVAILABLE, detail="eligibility unknown", **base
        )
    if elig not in (InstrumentEligibility.TRADEABLE, InstrumentEligibility.ACTIVE, InstrumentEligibility.LISTED):
        return StructureGateResult(allow=False, reason=BlockReason.NOT_TRADEABLE, detail=f"elig={elig.value}", **base)

    if mode == MarketStructure.HALTED:
        return StructureGateResult(allow=False, reason=BlockReason.TRADING_HALT, detail="halted", **base)
    if mode == MarketStructure.SUSPENDED:
        return StructureGateResult(allow=False, reason=BlockReason.SUSPENDED, detail="suspended", **base)
    if mode == MarketStructure.FCA:
        return StructureGateResult(allow=False, reason=BlockReason.FCA_INSTRUMENT, detail="Policy A FCA block", **base)
    if mode == MarketStructure.UNKNOWN:
        return StructureGateResult(
            allow=False, reason=BlockReason.MARKET_STRUCTURE_UNKNOWN, detail="UNKNOWN≠CONTINUOUS", **base
        )
    if mode != MarketStructure.CONTINUOUS:
        return StructureGateResult(allow=False, reason=BlockReason.POLICY_BLOCK, detail=mode.value, **base)

    if require_open_session:
        if session == TradingSession.UNKNOWN:
            return StructureGateResult(allow=False, reason=BlockReason.SESSION_UNKNOWN, detail="session unknown", **base)
        if session not in ALLOWED_SESSIONS:
            return StructureGateResult(
                allow=False,
                reason=BlockReason.SESSION_NOT_CONTINUOUS,
                detail=f"session={session.value} not OPEN",
                **base,
            )

    return StructureGateResult(allow=True, reason=BlockReason.NONE, detail="structure+session ok", **base)
