"""Instant Paper Portfolio — fills, ledger, P&L, TP/SL, reconstruction, no broker."""
from __future__ import annotations

from pathlib import Path

from src.python.ops.paper_portfolio import (
    DEFAULT_INITIAL_CAPITAL,
    PaperPortfolioStore,
    apply_exit,
    apply_long_entry,
    assert_no_broker_execution_imports,
    mark_to_market,
    new_session,
    performance_metrics,
    process_tp_sl_exits,
    process_tp_sl_exits_ohlc,
    rebuild_portfolio_from_trades,
    validate_portfolio_accounting,
)


def test_initial_portfolio():
    st = new_session()
    assert st.cash == DEFAULT_INITIAL_CAPITAL
    assert st.open_positions() == {}
    assert st.equity() == DEFAULT_INITIAL_CAPITAL


def test_buy_instant_paper_fill():
    st = new_session()
    st, trade, cls = apply_long_entry(
        st, symbol="ABDA", price=4972.0, weight=0.05, signal_id="sig_abda",
        timestamp="2026-09-15", fee_bps=15.0, slippage_bps=5.0,
    )
    assert cls == "FULL_FILL"
    assert trade is not None
    assert trade["status"] == "FILLED"
    assert trade["fill_price"] > 4972.0
    assert trade["fee"] > 0
    assert trade["net_cash_change"] < 0
    assert "ABDA" in st.open_positions()
    assert st.cash < DEFAULT_INITIAL_CAPITAL


def test_sell_instant_paper_fill():
    st = new_session()
    st, _, cls = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    assert cls == "FULL_FILL"
    st, trade, reason = apply_exit(
        st, symbol="BBCA", price=9100.0, timestamp="d2", reason="MANUAL", fee_bps=0, slippage_bps=0
    )
    assert trade is not None
    assert trade["status"] == "FILLED"
    assert "BBCA" not in st.open_positions()
    assert trade["pnl"] > 0


def test_insufficient_cash():
    st = new_session(initial_capital=1000.0)
    st, trade, cls = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.50, signal_id="s1",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    assert cls in ("SKIPPED_CASH", "SKIPPED_INVALID_DATA")
    assert trade is None


def test_insufficient_position_exit():
    st = new_session()
    st, trade, cls = apply_exit(st, symbol="ZZZZ", price=100.0, timestamp="d1")
    assert cls == "NO_POSITION"
    assert trade is None


def test_fee_and_slippage_on_buy():
    st = new_session()
    ref = 1000.0
    st, trade, cls = apply_long_entry(
        st, symbol="TEST", price=ref, weight=0.05, signal_id="fee1",
        timestamp="d1", fee_bps=15.0, slippage_bps=5.0,
    )
    assert cls == "FULL_FILL"
    assert trade["fill_price"] == ref * (1.0 + 5.0 / 10000.0)
    assert trade["fee"] > 0


def test_abda_no_double_entry_default_policy():
    """Regression: same symbol day2 must NOT scale-in under ops default."""
    st = new_session()
    cash0 = st.cash
    st, t1, c1 = apply_long_entry(
        st, symbol="ABDA", price=4962.0, weight=0.05, signal_id="sig_2026-09-15_ABDA",
        timestamp="2026-09-15", fee_bps=15.0, slippage_bps=5.0,
    )
    assert c1 == "FULL_FILL" and t1 is not None
    cash1 = st.cash
    assert cash1 < cash0
    assert abs(cash0 - cash1 - t1["total_cost"]) < 1e-6
    lots1 = st.open_positions()["ABDA"].qty / 100.0
    entry1 = st.open_positions()["ABDA"].avg_entry

    st, t2, c2 = apply_long_entry(
        st, symbol="ABDA", price=4972.0, weight=0.05, signal_id="sig_2026-09-16_ABDA",
        timestamp="2026-09-16", fee_bps=15.0, slippage_bps=5.0,
    )
    assert c2 == "SKIPPED_EXISTING_POSITION"
    assert t2 is None
    assert st.cash == cash1
    assert abs(st.open_positions()["ABDA"].qty / 100.0 - lots1) < 1e-9
    assert abs(st.open_positions()["ABDA"].avg_entry - entry1) < 1e-9


def test_scale_in_opt_in_averages_and_debits_cash():
    st = new_session()
    st, t1, c1 = apply_long_entry(
        st, symbol="ABDA", price=4962.0, weight=0.05, signal_id="s1",
        timestamp="2026-09-15", fee_bps=0, slippage_bps=0, allow_scale_in=True,
    )
    assert c1 == "FULL_FILL"
    cash1 = st.cash
    st, t2, c2 = apply_long_entry(
        st, symbol="ABDA", price=4972.0, weight=0.05, signal_id="s2",
        timestamp="2026-09-16", fee_bps=0, slippage_bps=0, allow_scale_in=True,
    )
    assert c2 == "FULL_FILL" and t2 is not None
    assert t2.get("scale_in") is True
    assert st.cash < cash1
    assert abs(cash1 - st.cash - t2["total_cost"]) < 1e-6
    pos = st.open_positions()["ABDA"]
    assert pos.qty >= 200.0 - 1e-6
    assert 4962.0 - 1e-6 <= pos.avg_entry <= 4972.0 + 1e-6


def test_cooldown_after_exit():
    st = new_session()
    st, _, c1 = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="s1",
        timestamp="2026-09-01", fee_bps=0, slippage_bps=0,
    )
    assert c1 == "FULL_FILL"
    st, _, r = apply_exit(st, symbol="BBCA", price=9100.0, timestamp="2026-09-02", fee_bps=0, slippage_bps=0)
    assert r != "NO_POSITION"
    st, _, c2 = apply_long_entry(
        st, symbol="BBCA", price=9050.0, weight=0.10, signal_id="s2",
        timestamp="2026-09-03", fee_bps=0, slippage_bps=0, min_reentry_days=5,
    )
    assert c2 == "SKIPPED_COOLDOWN"
    st, _, c3 = apply_long_entry(
        st, symbol="BBCA", price=9050.0, weight=0.10, signal_id="s3",
        timestamp="2026-09-10", fee_bps=0, slippage_bps=0, min_reentry_days=5,
    )
    assert c3 == "FULL_FILL"
