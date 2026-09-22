"""GitHub Actions runtime & operational hardening — synthetic, no live services."""
from __future__ import annotations

from pathlib import Path

from src.python.ops.runtime_cycle import (
    EXIT_HARD_FAIL,
    EXIT_OK,
    classify_exit,
    concurrency_group_operational,
    make_cycle_id,
    schedule_is_weekday_utc_cron,
    secret_scan_text,
    telegram_failure_does_not_mutate_ledger,
)
from src.python.ops.paper_portfolio import apply_long_entry, new_session, PaperPortfolioStore


def test_cycle_id_deterministic_for_same_inputs():
    a = make_cycle_id(trading_date="2026-09-19", workflow_run_id="12345", run_attempt="1", mode="OPERATIONAL")
    b = make_cycle_id(trading_date="2026-09-19", workflow_run_id="12345", run_attempt="1", mode="OPERATIONAL")
    assert a == b
    assert a.startswith("IDX-2026-09-19-")
    assert "12345" in a


def test_cycle_id_differs_by_attempt():
    a = make_cycle_id(trading_date="2026-09-19", workflow_run_id="9", run_attempt="1")
    b = make_cycle_id(trading_date="2026-09-19", workflow_run_id="9", run_attempt="2")
    assert a != b


def test_concurrency_group_per_market_date():
    assert concurrency_group_operational("2026-09-19") == "idx-operational-2026-09-19"


def test_schedule_cron_weekday_only():
    assert schedule_is_weekday_utc_cron("30 9 * * 1-5") is True
    assert schedule_is_weekday_utc_cron("0 2 * * 6") is False
    assert schedule_is_weekday_utc_cron("0 0 * * *") is False


def test_exit_codes_expected_vs_hard():
    code, _ = classify_exit({"status": "BLOCKED_SCHEDULE"})
    assert code == EXIT_OK
    code, _ = classify_exit({"status": "HALTED_DATA_QUALITY", "signals_generated": 0})
    assert code == EXIT_OK
    code, _ = classify_exit({"status": "HALTED_CORRUPT_PORTFOLIO"})
    assert code == EXIT_HARD_FAIL
    code, _ = classify_exit({"status": "OK", "live_execution": True})
    assert code == EXIT_HARD_FAIL


def test_telegram_isolation_contract():
    assert telegram_failure_does_not_mutate_ledger() is True


def test_telegram_failure_does_not_change_cash(tmp_path):
    store = PaperPortfolioStore(tmp_path / "pf.json", archive_dir=tmp_path / "s")
    state = new_session(initial_capital=10_000_000.0)
    state, trade, status = apply_long_entry(
        state, symbol="AAA", price=100.0, weight=0.05,
        signal_id="sig_tg_iso", timestamp="2026-09-19T09:00:00+00:00",
    )
    assert status == "PAPER_FILLED"
    cash_after_fill = state.cash
    store.save_atomic(state)
    report = {"status": "TELEGRAM_DELIVERY_FAILED", "paper_portfolio": {"cash": cash_after_fill}}
    code, _ = classify_exit(report)
    assert code == EXIT_OK
    reloaded = store.load()
    assert abs(reloaded.cash - cash_after_fill) < 1e-6


def test_rerun_idempotent_no_duplicate_fill(tmp_path):
    store = PaperPortfolioStore(tmp_path / "pf.json", archive_dir=tmp_path / "s")
    state = new_session(initial_capital=20_000_000.0)
    state, _, st1 = apply_long_entry(
        state, symbol="BBB", price=110.0, weight=0.05,
        signal_id="sig_rerun_1", timestamp="2026-09-19T09:00:00+00:00",
    )
    assert st1 == "PAPER_FILLED"
    store.save_atomic(state)
    state2 = store.load()
    state2, _, st2 = apply_long_entry(
        state2, symbol="BBB", price=110.0, weight=0.05,
        signal_id="sig_rerun_1", timestamp="2026-09-19T09:00:00+00:00",
    )
    assert st2 == "ALREADY_APPLIED"
    assert len(state2.trades) == 1


def test_secret_scan_catches_token_shape():
    hits = secret_scan_text("TELEGRAM_BOT_TOKEN=1234567890:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    assert "telegram_token" in hits
    assert secret_scan_text("telegram_status=SENT cycle_id=IDX-2026-09-19") == []


def test_idx_signal_workflow_has_runtime_guards():
    yml = Path(".github/workflows/idx_signal.yml").read_text(encoding="utf-8")
    assert "cron:" in yml
    assert "1-5" in yml
    assert "concurrency:" in yml
    assert "cancel-in-progress: false" in yml
    assert "secrets.TELEGRAM_BOT_TOKEN" in yml
    assert "echo $TELEGRAM" not in yml
    assert "cycle_id" in yml.lower() or "IDX_CYCLE_ID" in yml


def test_no_gui_in_src():
    src = Path("src/python")
    gui_hits = list(src.rglob("*gui*")) + list(src.rglob("*dashboard*"))
    assert gui_hits == [] or all("test" in str(p).lower() for p in gui_hits)
