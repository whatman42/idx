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
        st, symbol="BBCA", price=ref, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=15.0, slippage_bps=10.0,
    )
    assert cls == "FULL_FILL", cls
    assert abs(trade["fill_price"] - ref * (1.0 + 10.0 / 10000.0)) < 1e-6
    assert abs(trade["fee"] - trade["notional"] * 0.0015) < 1e-6
    assert trade["slippage_bps"] == 10.0


def test_average_cost_via_rebuild_multiple_buys():
    trades = [
        {
            "trade_id": "t1", "action": "BUY", "side": 1, "symbol": "X",
            "qty": 100, "fill_price": 1000, "fee": 0, "timestamp": "d1", "tp": 0, "sl": 0,
        },
        {
            "trade_id": "t2", "action": "BUY", "side": 1, "symbol": "X",
            "qty": 100, "fill_price": 1200, "fee": 0, "timestamp": "d2", "tp": 0, "sl": 0,
        },
    ]
    st = rebuild_portfolio_from_trades(trades)
    pos = st.open_positions()["X"]
    assert pos.qty == 200
    assert abs(pos.avg_entry - 1100.0) < 1e-6


def test_realized_unrealized_pnl():
    st = new_session()
    st, _, _ = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    qty = st.open_positions()["BBCA"].qty
    st = mark_to_market(st, {"BBCA": 9100.0}, "d1b")
    upnl = st.open_positions()["BBCA"].unrealized_pnl(9100.0)
    assert abs(upnl - qty * 100) < 1.0
    st, trade, _ = apply_exit(
        st, symbol="BBCA", price=9100.0, timestamp="d2", reason="TP_HIT", fee_bps=0, slippage_bps=0
    )
    assert trade["pnl"] > 0
    assert abs(st.realized_pnl - trade["pnl"]) < 1.0


def test_tp_execution_mark():
    st = new_session()
    st, _, _ = apply_long_entry(
        st, symbol="BBCA", price=10000.0, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=0, slippage_bps=0, tp=10600.0, sl=9700.0,
    )
    st, closed = process_tp_sl_exits(st, {"BBCA": 10650.0}, "d2", fee_bps=0, slippage_bps=0)
    assert len(closed) == 1
    assert closed[0]["reason"] == "TP_HIT"
    assert "BBCA" not in st.open_positions()


def test_sl_execution_mark():
    st = new_session()
    st, _, _ = apply_long_entry(
        st, symbol="BBCA", price=10000.0, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=0, slippage_bps=0, tp=10600.0, sl=9700.0,
    )
    st, closed = process_tp_sl_exits(st, {"BBCA": 9600.0}, "d2", fee_bps=0, slippage_bps=0)
    assert len(closed) == 1
    assert closed[0]["reason"] == "SL_HIT"


def test_tp_sl_same_candle_sl_precedence():
    st = new_session()
    st, _, _ = apply_long_entry(
        st, symbol="BBCA", price=10000.0, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=0, slippage_bps=0, tp=10600.0, sl=9700.0,
    )
    st, closed = process_tp_sl_exits_ohlc(
        st,
        {"BBCA": {"high": 10700.0, "low": 9600.0, "close": 10100.0}},
        "d2",
        fee_bps=0,
        slippage_bps=0,
    )
    assert len(closed) == 1
    assert closed[0]["reason"] == "SL_HIT"


def test_equity_equals_cash_plus_mv():
    st = new_session()
    st, _, _ = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    marks = {"BBCA": 9000.0}
    assert abs(st.equity(marks) - (st.cash + st.market_value(marks))) < 1.0
    errs = validate_portfolio_accounting(st, marks)
    assert errs == [], errs


def test_equity_curve_snapshot():
    st = new_session()
    st, _, _ = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    assert len(st.equity_ledger) >= 1
    snap = st.equity_ledger[-1]
    assert "equity" in snap and "cash" in snap


def test_performance_metrics_no_closed():
    st = new_session()
    m = performance_metrics(st)
    assert m["win_rate"] is None
    assert m["profit_factor"] is None
    assert "N/A" in (m.get("sample_note") or "")


def test_performance_metrics_after_close():
    st = new_session()
    st, _, _ = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    st, _, _ = apply_exit(
        st, symbol="BBCA", price=9500.0, timestamp="d2", reason="TP_HIT", fee_bps=0, slippage_bps=0
    )
    m = performance_metrics(st)
    assert m["closed_trades"] == 1
    assert m["win_rate"] == 1.0


def test_persistence_and_restart(tmp_path):
    store = PaperPortfolioStore(tmp_path / "pp.json")
    st = new_session()
    st, trade, cls = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    store.save_atomic(st)
    st2 = store.load()
    assert "BBCA" in st2.open_positions()
    assert st2.cash == st.cash


def test_reconstruction_matches_live():
    st = new_session()
    st, _, _ = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="s1",
        timestamp="d1", fee_bps=15.0, slippage_bps=5.0,
    )
    rebuilt = rebuild_portfolio_from_trades(list(st.trades), initial_capital=DEFAULT_INITIAL_CAPITAL)
    assert abs(rebuilt.cash - st.cash) < 1.0
    assert "BBCA" in rebuilt.open_positions()


def test_idempotency_duplicate_signal():
    st = new_session()
    st, _, c1 = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="same",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    st, _, c2 = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="same",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    assert c1 == "FULL_FILL"
    assert c2 == "ALREADY_APPLIED"


def test_no_broker_execution_in_paper_module():
    src = Path("src/python/ops/paper_portfolio.py").read_text()
    hits = assert_no_broker_execution_imports(src)
    assert hits == [], hits
    assert "BrokerOrderExecutor" not in src
    assert "from src.python.broker" not in src


def test_determinism_same_input_same_fill():
    def run():
        st = new_session()
        st, trade, cls = apply_long_entry(
            st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="sig",
            timestamp="2026-09-15", fee_bps=15.0, slippage_bps=5.0,
        )
        return cls, trade["fill_price"], trade["fee"], st.cash

    assert run() == run()


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
    assert st.cash == cash1  # cash must not move on skip
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
    assert pos.qty >= 200.0 - 1e-6  # at least 2 lots of 100 if sized that way
    # avg between 4962 and 4972
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


def test_equity_invariant_cash_plus_mv():
    st = new_session()
    st, _, cls = apply_long_entry(
        st, symbol="ABDA", price=4962.0, weight=0.05, signal_id="inv1",
        timestamp="2026-09-15", fee_bps=15.0, slippage_bps=5.0,
    )
    assert cls == "FULL_FILL"
    marks = {"ABDA": 4960.0}
    st = mark_to_market(st, marks, "2026-09-15")
    eq = st.equity(marks)
    assert abs(eq - (st.cash + st.market_value(marks))) < 1.0  # 1 rupiah tolerance
    errs = validate_portfolio_accounting(st, marks)
    assert errs == [], errs


def test_replay_sep15_16_abda_one_lot():
    """Replay: only day-1 BUY in trades → 1 lot @~4962; day-2 not in ledger if skipped."""
    st = new_session()
    st, t1, c1 = apply_long_entry(
        st, symbol="ABDA", price=4962.0, weight=0.05, signal_id="sig_2026-09-15_ABDA",
        timestamp="2026-09-15", fee_bps=15.0, slippage_bps=5.0,
    )
    assert c1 == "FULL_FILL"
    cash_after_d1 = st.cash
    st, t2, c2 = apply_long_entry(
        st, symbol="ABDA", price=4972.0, weight=0.05, signal_id="sig_2026-09-16_ABDA",
        timestamp="2026-09-16", fee_bps=15.0, slippage_bps=5.0,
    )
    assert c2 == "SKIPPED_EXISTING_POSITION"
    # rebuild from trades must match live state (only 1 BUY)
    rebuilt = rebuild_portfolio_from_trades(st.trades, initial_capital=DEFAULT_INITIAL_CAPITAL)
    assert "ABDA" in rebuilt.open_positions()
    pos = rebuilt.open_positions()["ABDA"]
    assert abs(pos.qty - 100.0) < 1e-6 or pos.qty >= 100.0  # at least 1 lot
    assert abs(rebuilt.cash - cash_after_d1) < 1.0
    # avg_entry near day-1 fill (with slippage)
    assert abs(pos.avg_entry - t1["fill_price"]) < 1e-6


def test_signal_id_idempotent_same_order():
    st = new_session()
    st, t1, c1 = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="same_sig",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    assert c1 == "FULL_FILL"
    cash1 = st.cash
    st, t2, c2 = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="same_sig",
        timestamp="d1", fee_bps=0, slippage_bps=0,
    )
    assert c2 == "ALREADY_APPLIED"
    assert t2 is None
    assert st.cash == cash1


def test_time_stop_exit():
    st = new_session()
    st, t1, c1 = apply_long_entry(
        st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="ts1",
        timestamp="2026-09-01", fee_bps=0, slippage_bps=0,
        time_stop_bars=3, trailing_pct=0.0,
    )
    assert c1 == "FULL_FILL"
    # day+1, +2: still open (mark between SL/TP)
    st, closed = process_tp_sl_exits(st, {"BBCA": 9100.0}, "2026-09-02", fee_bps=0, slippage_bps=0)
    assert closed == []
    st, closed = process_tp_sl_exits(st, {"BBCA": 9100.0}, "2026-09-03", fee_bps=0, slippage_bps=0)
    assert closed == []
    # day+3 from entry (>=3 days) -> TIME_STOP
    st, closed = process_tp_sl_exits(st, {"BBCA": 9100.0}, "2026-09-04", fee_bps=0, slippage_bps=0)
    assert len(closed) == 1
    assert closed[0]["reason"] == "TIME_STOP"
    assert "BBCA" not in st.open_positions()


def test_trailing_stop_ratchets_and_exits():
    st = new_session()
    st, t1, c1 = apply_long_entry(
        st, symbol="TLKM", price=4000.0, weight=0.10, signal_id="tr1",
        timestamp="2026-09-01", fee_bps=0, slippage_bps=0,
        tp=5000.0, sl=3800.0, trailing_pct=0.05, time_stop_bars=0,
    )
    assert c1 == "FULL_FILL"
    # price rises -> peak updates, SL trails to 95% of peak
    st, closed = process_tp_sl_exits(st, {"TLKM": 4400.0}, "2026-09-02", fee_bps=0, slippage_bps=0)
    assert closed == []
    pos = st.open_positions()["TLKM"]
    assert pos.peak_mark >= 4400.0 - 1e-9
    assert pos.sl >= 4400.0 * 0.95 - 1.0  # trailed up
    # drop through trailed SL
    trail_sl = float(pos.sl)
    st, closed = process_tp_sl_exits(st, {"TLKM": trail_sl - 1.0}, "2026-09-03", fee_bps=0, slippage_bps=0)
    assert len(closed) == 1
    assert closed[0]["reason"] == "SL_HIT"


def test_exit_plan_atr_vs_static():
    from src.python.strategy.exits import build_exit_plan
    plan = build_exit_plan(entry_price=1000.0, atr=20.0, time_stop_bars=5, trailing_pct=0.03)
    assert plan.method.startswith("atr")
    assert plan.sl_pct > 0 and plan.tp_pct > plan.sl_pct
    assert plan.time_stop_bars == 5
    plan2 = build_exit_plan(entry_price=1000.0, atr=None, time_stop_bars=5)
    assert plan2.method == "static_pct"
    assert abs(plan2.sl_pct - 0.03) < 1e-9 and abs(plan2.tp_pct - 0.06) < 1e-9
