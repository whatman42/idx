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
