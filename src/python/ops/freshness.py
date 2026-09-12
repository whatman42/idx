from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Any, Optional
import pandas as pd
from src.python.market.calendar import IDX_TZ, TradingCalendar, is_stale

JKT = IDX_TZ

def expected_trading_day(now: Optional[datetime] = None, calendar: Optional[TradingCalendar] = None) -> date:
    now = now or datetime.now(JKT)
    if now.tzinfo is None:
        now = now.replace(tzinfo=JKT)
    local = now.astimezone(JKT)
    d = local.date()
    cal = calendar or TradingCalendar()
    for _ in range(14):
        if cal.is_trading_day(d):
            return d
        d -= timedelta(days=1)
    return local.date()

def latest_bar_date(bars: pd.DataFrame) -> Optional[date]:
    if bars is None or bars.empty or "timestamp" not in bars.columns:
        return None
    ts = pd.to_datetime(bars["timestamp"])
    last = ts.max()
    if hasattr(last, "to_pydatetime"):
        last = last.to_pydatetime()
    if getattr(last, "tzinfo", None) is None:
        last = last.replace(tzinfo=JKT)
    return last.astimezone(JKT).date()

def freshness_gate(
    bars: pd.DataFrame,
    *,
    now: Optional[datetime] = None,
    calendar: Optional[TradingCalendar] = None,
    require_current_day: bool = True,
    max_stale_days: float = 2.0,
    allow_last_session_on_holiday: bool = True,
) -> dict[str, Any]:
    """On weekend/holiday: PASS if bars end on last expected trading day."""
    now = now or datetime.now(JKT)
    if now.tzinfo is None:
        now = now.replace(tzinfo=JKT)
    cal = calendar or TradingCalendar()
    local_date = now.astimezone(JKT).date()
    exp = expected_trading_day(now, cal)
    last = latest_bar_date(bars)
    is_holiday = not cal.is_trading_day(local_date)

    if last is None:
        return {
            "status": "BLOCKED",
            "reason": "NO_BARS",
            "local_date": str(local_date),
            "expected_trading_day": str(exp),
        }

    last_ts = pd.to_datetime(bars["timestamp"]).max()
    if hasattr(last_ts, "to_pydatetime"):
        last_ts = last_ts.to_pydatetime()
    if is_stale(last_ts, now=now, max_age_days=max_stale_days):
        return {
            "status": "BLOCKED",
            "reason": "STALE_MAX_AGE",
            "latest_bar_date": str(last),
            "expected_trading_day": str(exp),
            "local_date": str(local_date),
        }

    if is_holiday and allow_last_session_on_holiday:
        if last == exp:
            return {
                "status": "PASS",
                "reason": "LAST_SESSION_OK_NON_TRADING_DAY",
                "latest_bar_date": str(last),
                "expected_trading_day": str(exp),
                "local_date": str(local_date),
            }
        return {
            "status": "BLOCKED",
            "reason": "STALE_NOT_LAST_SESSION",
            "latest_bar_date": str(last),
            "expected_trading_day": str(exp),
            "local_date": str(local_date),
        }

    if require_current_day and last < exp:
        return {
            "status": "BLOCKED",
            "reason": "STALE_NOT_CURRENT_TRADING_DAY",
            "latest_bar_date": str(last),
            "expected_trading_day": str(exp),
            "local_date": str(local_date),
        }
    if last > exp:
        return {
            "status": "BLOCKED",
            "reason": "FUTURE_BARS",
            "latest_bar_date": str(last),
            "expected_trading_day": str(exp),
        }
    return {
        "status": "PASS",
        "reason": "OK",
        "latest_bar_date": str(last),
        "expected_trading_day": str(exp),
        "local_date": str(local_date),
    }
