"""Corporate Action Event Guard — facts → CA_CLEAR | CA_REVIEW | CA_BLOCK.

Never emits BUY/SELL/HOLD. NO_DATA is never silent PASS (uses CA_REVIEW or BLOCK).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from src.python.idx_enrichment.models import (
    CAOutcome,
    CorporateActionEvent,
    CorporateActionType,
    DataAuthority,
    DataPresence,
    EnrichmentDecision,
)
from src.python.idx_enrichment.policy import DEFAULT_POLICY, EnrichmentPolicy, resolve_presence

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
    try:
        return datetime.strptime(str(s).strip()[:10], "%Y-%m-%d").date()
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
    return (anchor - timedelta(days=max(0, before_days))) <= td <= (anchor + timedelta(days=max(0, after_days)))


def evaluate_corporate_actions(
    symbol: str,
    trading_date: str,
    events: Iterable[CorporateActionEvent],
    *,
    policy: Optional[EnrichmentPolicy] = None,
    before_days: int = DEFAULT_BLACKOUT_BEFORE_DAYS,
    after_days: int = DEFAULT_BLACKOUT_AFTER_DAYS,
) -> EnrichmentDecision:
    pol = policy or DEFAULT_POLICY
    sym = str(symbol).upper().strip()
    ev_list = [e for e in (events or []) if str(e.symbol).upper().strip() == sym]

    material_with_dates: list[CorporateActionEvent] = []
    material_no_dates: list[CorporateActionEvent] = []
    for ev in ev_list:
        if ev.action_type not in MATERIAL_ACTIONS:
            continue
        if _anchor_date(ev):
            material_with_dates.append(ev)
        else:
            material_no_dates.append(ev)

    if material_no_dates and not material_with_dates and not [
        e for e in ev_list if e.action_type not in MATERIAL_ACTIONS
    ]:
        return EnrichmentDecision(
            allow=False,
            outcome=CAOutcome.CA_BLOCK.value,
            reason="INVALID_CA_RECORD",
            layer="corporate_action",
            authority=DataAuthority.CONDITIONAL_GATE.value,
            presence=DataPresence.INVALID.value,
            detail="material CA without effective/ex date",
            symbols_affected=[sym],
        )

    if not ev_list:
        presence = DataPresence.NO_DATA
        if pol.ca_on_no_data == "BLOCK":
            return EnrichmentDecision(
                allow=False,
                outcome=CAOutcome.CA_BLOCK.value,
                reason="CA_NO_DATA_BLOCK",
                layer="corporate_action",
                authority=DataAuthority.CONDITIONAL_GATE.value,
                presence=presence.value,
                detail="no CA cache — policy BLOCK",
                symbols_affected=[sym],
            )
        return EnrichmentDecision(
            allow=True,
            outcome=CAOutcome.CA_REVIEW.value,
            reason="CA_NO_DATA_REVIEW",
            layer="corporate_action",
            authority=DataAuthority.CONDITIONAL_GATE.value,
            presence=presence.value,
            detail="no CA cache — not certified clear; review flag only",
            symbols_affected=[sym],
        )

    as_ofs = []
    for e in ev_list:
        ao = getattr(e.provenance, "as_of", "") or ""
        if ao:
            as_ofs.append(ao)
    as_of = max(as_ofs) if as_ofs else ""
    presence = resolve_presence(
        has_record=True,
        as_of=as_of,
        trading_date=trading_date,
        max_stale_days=pol.max_stale_days,
    )
    if presence == DataPresence.STALE:
        if pol.ca_on_stale == "BLOCK":
            return EnrichmentDecision(
                allow=False,
                outcome=CAOutcome.CA_BLOCK.value,
                reason="CA_STALE_BLOCK",
                layer="corporate_action",
                authority=DataAuthority.CONDITIONAL_GATE.value,
                presence=presence.value,
                detail=f"CA cache as_of={as_of} stale vs {trading_date}",
                symbols_affected=[sym],
            )
        return EnrichmentDecision(
            allow=True,
            outcome=CAOutcome.CA_REVIEW.value,
            reason="CA_STALE_REVIEW",
            layer="corporate_action",
            authority=DataAuthority.CONDITIONAL_GATE.value,
            presence=presence.value,
            detail=f"CA cache stale as_of={as_of}",
            symbols_affected=[sym],
        )

    in_blackout = [e for e in material_with_dates if event_in_blackout(e, trading_date, before_days=before_days, after_days=after_days)]
    if in_blackout and pol.ca_blackout_block:
        kinds = sorted({e.action_type.value for e in in_blackout})
        return EnrichmentDecision(
            allow=False,
            outcome=CAOutcome.CA_BLOCK.value,
            reason="CA_BLACKOUT",
            layer="corporate_action",
            authority=DataAuthority.CONDITIONAL_GATE.value,
            presence=DataPresence.DATA_PRESENT.value,
            detail=f"CA blackout: {','.join(kinds)} near {trading_date}",
            symbols_affected=[sym],
        )

    return EnrichmentDecision(
        allow=True,
        outcome=CAOutcome.CA_CLEAR.value,
        reason="CA_CLEAR",
        layer="corporate_action",
        authority=DataAuthority.CONDITIONAL_GATE.value,
        presence=DataPresence.DATA_PRESENT.value,
        detail="no material CA in blackout window",
        symbols_affected=[sym],
    )
