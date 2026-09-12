from typer.testing import CliRunner
from src.python.ops.signal_bot import app

def test_test_mode_runs():
    r = CliRunner().invoke(app, ["--mode", "TEST", "--force-schedule", "--symbols", "BBCA"])
    assert r.exit_code == 0, r.output

def test_weekday_training_blocked(monkeypatch, tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from src.python.training import weekend_train as wt
    class FakeClock:
        def now(self):
            return datetime(2026, 9, 8, 10, 0, tzinfo=ZoneInfo("Asia/Jakarta"))
    monkeypatch.setattr(wt, "SystemClock", FakeClock)
    monkeypatch.delenv("EMERGENCY_TRAINING", raising=False)
    result = CliRunner().invoke(wt.app, ["--budget-sec", "600", "--out-dir", str(tmp_path / "cand")])
    assert result.exit_code == 0
    assert "TRAINING_BLOCKED_WEEKDAY" in result.output
