from __future__ import annotations
from datetime import date, datetime
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd
from src.python.market.calendar import is_trading_day
from src.python.ops.freshness import freshness_gate
from src.python.scheduler.schedule import classify_schedule, ScheduleType

JKT = ZoneInfo("Asia/Jakarta")

def _bars_ending(last: date, n: int = 30, sym: str = "BBCA") -> pd.DataFrame:
    idx = pd.bdate_range(end=pd.Timestamp(last), periods=n)
    px = np.linspace(100, 110, len(idx))
    return pd.DataFrame({"timestamp": idx, "symbol": sym, "open": px, "high": px+1, "low": px-1, "close": px, "volume": 1e6})

def test_schedule_cron_maps_to_1630_jakarta():
    utc = datetime(2026, 9, 7, 9, 30, tzinfo=ZoneInfo("UTC"))
    jkt = utc.astimezone(JKT)
    assert jkt.hour == 16 and jkt.minute == 30

def test_holiday_not_trading_day():
    assert is_trading_day(date(2026, 1, 1)) is False

def test_freshness_current_day_allow():
    now = datetime(2026, 9, 7, 16, 30, tzinfo=JKT)
    bars = _bars_ending(date(2026, 9, 7))
    assert freshness_gate(bars, now=now, require_current_day=True)["status"] == "PASS"

def test_freshness_stale_block():
    now = datetime(2026, 9, 7, 16, 30, tzinfo=JKT)
    bars = _bars_ending(date(2026, 9, 4))
    fg = freshness_gate(bars, now=now, require_current_day=True, max_stale_days=10)
    assert fg["status"] == "BLOCKED"

def test_saturday_training_allowed():
    class FakeClock:
        def now(self):
            return datetime(2026, 9, 5, 10, 0, tzinfo=JKT)
    plan = classify_schedule(FakeClock())
    assert plan.allow_training is True
    assert plan.schedule_type == ScheduleType.SATURDAY_EXPLORATION

def test_tplus1_label():
    from src.python.validation.economic_sim import simulate_long_only
    from src.python.data.costs import CostModel
    bars = _bars_ending(date(2026, 9, 7), n=40)
    sig = bars[["timestamp", "symbol"]].assign(side=1)
    sim = simulate_long_only(bars, sig, cost=CostModel(0, 0), hold_bars=3)
    assert sim["metrics"]["timing"] == "signal_T_execute_open_Tplus1"

def test_no_live_ops_paths():
    """No live broker order *call sites* in ops (guard regex strings may mention names)."""
    from pathlib import Path
    import re
    call_re = re.compile(r"\b(place_order|execute_live)\s*\(")
    for p in Path("src/python/ops").rglob("*.py"):
        text = p.read_text()
        assert not call_re.search(text), f"live order call in {p}"
