"""Corporate Action Event Guard — hard/conditional protection around CA windows.

Does NOT generate BUY signals. Blocks or flags entries when price moves may be CA-driven.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from src.python.idx_enrichment.models import (
    CorporateActionEvent,
    CorporateActionType,
    DataAuthority,
    EnrichmentDecision,
    EventGuardDecision,
)

DEFAULT_BLACKOUT_BEFORE_DAYS = 1
DEFAULT_BLACKOUT_AFTER_DAYS = 1

MATERIAL_ACTIONS = {
    CorporateActionType.STOCK_SPLIT,
    CorporateActionType.REVERSE_SPLIT,
    CorporateActionType.RIGHTS_ISSUE,
    CorporateActionType.WARRANT,
    CorporateActionType.ADDITIONAL_SHARES,
    CorporateActionType.DIVIDEND,
}


def _parse_day(s: str) -> Optional[date]:
    if not s:
        return None
    s = str(s).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _anchor_date(ev: CorporateActionEvent) -> Optional[date]:
    for key in (ev.ex_date, ev.effective_date, ev.cum_date, ev.record_date, ev.announcement_date):
        d = _parse_day(key)
        if d:
            return d
    return None


def event_in_blackout(
    ev: CorporateActionEvent,
    trading_date: str,
    *,
    before_days: int = DEFAULT_BLACKOUT_BEFORE_DAYS,
    after_days: int = DEFAULT_BLACKOUT_AFTER_DAYS,
) -> bool:
    td = _parse_day(trading_date)
    anchor = _anchor_date(ev)
    if not td or not anchor:
        return False
    start = anchor - timedelta(days=max(0, before_days))
    end = anchor + timedelta(days=max(0, after_days))
    return start <= td <= end


def evaluate_corporate_actions(
    symbol: str,
    trading_date: str,
    events: Iterable[CorporateActionEvent],
    *,
    before_days: int = DEFAULT_BLACKOUT_BEFORE_DAYS,
    after_days: int = DEFAULT_BLACKOUT_AFTER_DAYS,
) -> EnrichmentDecision:
    sym = str(symbol).upper().strip()
    material: list[CorporateActionEvent] = []
    any_events = False
    for ev in events or []:
        if str(ev.symbol).upper().strip() != sym:
            continue
        any_events = True
        if ev.action_type not in MATERIAL_ACTIONS:
            continue
        if event_in_blackout(ev, trading_date, before_days=before_days, after_days=after_days):
            material.append(ev)

    if material:
        kinds = sorted({e.action_type.value for e in material})
        return EnrichmentDecision(
            allow=False,
            reason=EventGuardDecision.DATA_EVENT_REVIEW.value,
            layer="corporate_action",
            authority=DataAuthority.CONDITIONAL_GATE.value,
            detail=f"CA blackout: {','.join(kinds)} near {trading_date}",
            symbols_affected=[sym],
        )
    if not any_events:
        return EnrichmentDecision(
            allow=True,
            reason=EventGuardDecision.NO_DATA.value,
            layer="corporate_action",
            authority=DataAuthority.CONDITIONAL_GATE.value,
            detail="no corporate-action cache for symbol",
            symbols_affected=[sym],
        )
    return EnrichmentDecision(
        allow=True,
        reason=EventGuardDecision.PASS.value,
        layer="corporate_action",
        authority=DataAuthority.CONDITIONAL_GATE.value,
        detail="no material CA in blackout window",
        symbols_affected=[sym],
    )
