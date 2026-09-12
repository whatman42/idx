from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from zoneinfo import ZoneInfo
from src.python.market.calendar import is_trading_day as cal_is_trading_day

JKT = ZoneInfo("Asia/Jakarta")

class ScheduleType(str, Enum):
    WEEKDAY_PRODUCTION = "WEEKDAY_PRODUCTION"
    SATURDAY_EXPLORATION = "SATURDAY_EXPLORATION"
    SUNDAY_VALIDATION = "SUNDAY_VALIDATION"
    NON_TRADING_DAY = "NON_TRADING_DAY"
    OUTSIDE_WINDOW = "OUTSIDE_WINDOW"

@dataclass
class RunPlan:
    schedule_type: ScheduleType
    trading_date: date
    cycle_key: str
    allow_training: bool
    allow_promotion: bool
    allow_new_trades: bool
    reason: str

class SystemClock:
    def now(self) -> datetime:
        return datetime.now(JKT)

class TrainingDeadline:
    def __init__(self, internal_budget_sec: float = 1200):
        self.budget = internal_budget_sec
        self._t0 = 0.0
    def start(self, clock: SystemClock) -> None:
        import time
        self._t0 = time.monotonic()
    def remaining_sec(self, clock: SystemClock) -> float:
        import time
        return max(0.0, self.budget - (time.monotonic() - self._t0))
    def expired(self, clock: SystemClock) -> bool:
        return self.remaining_sec(clock) <= 0

def production_cycle_key(d: date) -> str:
    return f"IDX_PRODUCTION:{d.isoformat()}"

def training_run_key(d: date, stage: str) -> str:
    return f"IDX_TRAIN:{d.isoformat()}:{stage}"

def classify_schedule(clock: SystemClock, is_trading_day: bool | None = None) -> RunPlan:
    now = clock.now()
    d = now.date()
    trading = is_trading_day if is_trading_day is not None else cal_is_trading_day(d)
    if d.weekday() == 5:
        return RunPlan(ScheduleType.SATURDAY_EXPLORATION, d, training_run_key(d, "exploration"),
                       True, False, False, "saturday_exploration")
    if d.weekday() == 6:
        return RunPlan(ScheduleType.SUNDAY_VALIDATION, d, training_run_key(d, "validation"),
                       True, True, False, "sunday_validation")
    if not trading:
        return RunPlan(ScheduleType.NON_TRADING_DAY, d, production_cycle_key(d),
                       False, False, False, "non_trading_day")
    minutes = now.hour * 60 + now.minute
    if minutes < 15 * 60 + 30:
        return RunPlan(ScheduleType.OUTSIDE_WINDOW, d, production_cycle_key(d),
                       False, False, False, "before_market_close")
    return RunPlan(ScheduleType.WEEKDAY_PRODUCTION, d, production_cycle_key(d),
                   False, False, True, "weekday_eod_production")
