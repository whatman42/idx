from __future__ import annotations
from datetime import date, datetime, time
from typing import Callable, Optional, Set
from zoneinfo import ZoneInfo

IDX_TZ = ZoneInfo("Asia/Jakarta")
SESSION_OPEN = time(9, 0)
SESSION_CLOSE = time(15, 50)

_SEED_HOLIDAYS: Set[date] = {
    date(2026, 1, 1), date(2026, 3, 19), date(2026, 3, 20), date(2026, 5, 1),
    date(2026, 5, 14), date(2026, 5, 15), date(2026, 6, 1), date(2026, 8, 17),
    date(2026, 12, 25), date(2026, 12, 31),
}

class TradingCalendar:
    def __init__(self, extra_holidays: Optional[Set[date]] = None,
                 provider: Optional[Callable[[date], bool]] = None):
        self._holidays = set(_SEED_HOLIDAYS)
        if extra_holidays:
            self._holidays |= set(extra_holidays)
        self._provider = provider

    def is_weekday(self, d: date) -> bool:
        return d.weekday() < 5

    def is_trading_day(self, d: date) -> bool:
        if self._provider is not None:
            try:
                return bool(self._provider(d))
            except Exception:
                pass
        if not self.is_weekday(d):
            return False
        if d in self._holidays:
            return False
        return True

_DEFAULT = TradingCalendar()

def is_weekday(d: date) -> bool:
    return _DEFAULT.is_weekday(d)

def is_trading_day(d: date, calendar: Optional[TradingCalendar] = None) -> bool:
    return (calendar or _DEFAULT).is_trading_day(d)

def is_stale(last_bar_ts: datetime, now: datetime | None = None, max_age_days: float = 5.0) -> bool:
    now = now or datetime.now(IDX_TZ)
    if last_bar_ts.tzinfo is None:
        last_bar_ts = last_bar_ts.replace(tzinfo=IDX_TZ)
    if now.tzinfo is None:
        now = now.replace(tzinfo=IDX_TZ)
    age = (now - last_bar_ts.astimezone(IDX_TZ)).total_seconds() / 86400.0
    return age > max_age_days
