"""Financial integrity, lot/share, portfolio recon, LLM boundary, BBCA golden regression."""
from __future__ import annotations

import pytest

from src.python.reporting.finance import (
    SHARES_PER_LOT,
    exposure_pct,
    lots_from_shares,
    position_value,
    reward_risk_ratio,
    risk_amount,
    risk_pct,
    shares_from_lots,
    unrealized_pnl_long,
    realized_pnl_long,
)
from src.python.reporting.models import CycleReport, SignalReport
from src.python.reporting.builder import (
    build_buy_signal,
    build_cycle_report,
    build_open_position,
    build_portfolio_snapshot,
)
from src.python.reporting.validation import (
    validate_cycle_report,
    validate_position_math,
    validate_portfolio_math,
    validate_signal_report,
)
from src.python.reporting.composer import compose_telegram_message
from src.python.reporting.llm_boundary import safe_compose, validate_llm_output


def test_shares_per_lot_constant():
    assert SHARES_PER_LOT == 100


def test_lot_share_conversion():
    assert shares_from_lots(5) == 500
    assert lots_from_shares(500) == 5
    assert shares_from_lots(1) == 100


def test_bbca_golden_regression():
    """Permanent regression: 5 lot BBCA @ 9850 must never show 50 shares / 492500 / 2500 upnl."""
    equity = 10_120_000.0
    entry, mark, tp2, sl = 9850.0, 9900.0, 10441.0, 9555.0
    lots = 5.0
    shares = shares_from_lots(lots)
    pv = position_value(entry, shares)
    upnl = unrealized_pnl_long(mark, entry, shares)
    exp = exposure_pct(pv, equity)
    assert shares == 500
    assert pv == 4_925_000
    assert upnl == 25_000
    assert abs(exp - 48.67) < 0.05
    assert shares != 50
    assert pv != 492_500
    assert upnl != 2_500
    assert abs(exp - 20.0) > 1.0


def test_risk_and_rr():
    entry, tp, sl = 9850.0, 10441.0, 9555.0
    shares = 500.0
    ra = risk_amount(entry, sl, shares)
    assert abs(ra - (9850 - 9555) * 500) < 1e-6
    rr = reward_risk_ratio(entry, tp, sl)
    assert rr is not None and abs(rr - (10441 - 9850) / (9850 - 9555)) < 1e-9


def test_realized_pnl():
    assert realized_pnl_long(3890, 3800, 1000) == 90_000


def test_build_buy_signal_math():
    sig = build_buy_signal(
        signal_id="sig_test",
        timestamp="2026-09-14",
        symbol="BBCA",
        entry_reference=9850,
        stop_loss=9555,
        tp1=10150,
        tp2=10441,
        shares=500,
        equity=10_120_000,
        confidence=0.72,
        confidence_method="sma20_rank_score",
        model_version="ops_sma_v0",
        explanation=["Ranking #1 confidence vs SMA20"],
    )
    assert sig.lots == 5
    assert sig.position_value == 4_925_000
    assert sig.confidence == 72.0
    errs = validate_signal_report(sig)
    assert errs == [], errs


def test_portfolio_reconciliation():
    pos = build_open_position(
        symbol="BBCA", entry_price=9850, mark_price=9900, shares=500, tp=10441, sl=9555
    )
    assert pos.lots == 5
    assert pos.unrealized_pnl == 25_000
    assert pos.market_value == 4_950_000
    snap = build_portfolio_snapshot(
        {
            "cash": 5_195_000,
            "equity": 10_145_000,
            "realized_pnl": 0,
            "open_positions": {
                "BBCA": {
                    "avg_entry": 9850,
                    "last_mark": 9900,
                    "qty": 500,
                    "lots": 5,
                    "tp": 10441,
                    "sl": 9555,
                }
            },
        }
    )
    assert abs(snap.market_value - 4_950_000) < 1
    assert abs(snap.unrealized_pnl - 25_000) < 1
    errs = validate_portfolio_math(snap)
    assert errs == [], errs


def test_reject_50_shares_bug_in_signal_validation():
    sig = build_buy_signal(
        signal_id="x",
        timestamp="t",
        symbol="BBCA",
        entry_reference=9850,
        stop_loss=9555,
        tp1=10150,
        tp2=10441,
        shares=50,
        equity=10_120_000,
        confidence=72,
        confidence_method="test",
    )
    sig.lots = 5
    sig.shares = 50
    sig.position_value = 492_500
    errs = validate_signal_report(sig)
    assert any("shares_lots_mismatch" in e or "regression_bug" in e for e in errs)


def test_cycle_and_composer_bbca():
    sig = build_buy_signal(
        signal_id="sig_2026-09-14_BBCA_ops_sma_v0",
        timestamp="2026-09-14",
        symbol="BBCA",
        entry_reference=9850,
        stop_loss=9555,
        tp1=10150,
        tp2=10441,
        shares=500,
        equity=10_120_000,
        confidence=72,
        confidence_method="sma20_rank_score",
        model_version="ops_sma_v0",
        explanation=["Ranking #1 vs SMA20 universe"],
        entry_low=9800,
        entry_high=9875,
    )
    report = build_cycle_report(
        trading_date="2026-09-14",
        mode="PAPER",
        pf_summary={
            "cash": 5_195_000,
            "equity": 10_145_000,
            "realized_pnl": 45_200,
            "open_positions": {
                "BBCA": {
                    "avg_entry": 9850,
                    "last_mark": 9900,
                    "qty": 500,
                    "lots": 5,
                    "tp": 10441,
                    "sl": 9555,
                }
            },
        },
        signal=sig,
        exits=[
            {
                "symbol": "TLKM",
                "entry": 3800,
                "price": 3890,
                "qty": 1000,
                "lots": 10,
                "pnl": 90_000,
                "reason": "TP_HIT",
                "timestamp": "2026-09-14",
                "action": "SELL",
                "side": -1,
            }
        ],
        model_version="ops_sma_v0",
    )
    assert report.integrity_ok, report.integrity_errors
    text = compose_telegram_message(report)
    assert "BBCA" in text
    assert "500" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text or "MODE OPERASI" in text
    assert ("Skor Model" in text or "Model confidence" in text) and "72/100" in text


def test_llm_mutation_rejected():
    sig = build_buy_signal(
        signal_id="sid1",
        timestamp="t",
        symbol="BBCA",
        entry_reference=9850,
        stop_loss=9555,
        tp1=10150,
        tp2=10441,
        shares=500,
        equity=10_120_000,
        confidence=72,
        confidence_method="test",
    )
    report = build_cycle_report(
        trading_date="2026-09-14",
        mode="PAPER",
        pf_summary={"cash": 10_000_000, "equity": 10_000_000, "open_positions": {}},
        signal=sig,
    )
    bad = "🎯 SELL — BBCA\nEntry: Rp1\nNO LIVE EXECUTION"
    problems = validate_llm_output(bad, report)
    assert problems
    text, src = safe_compose(report, llm_text=bad, llm_enabled=True)
    assert src == "deterministic_fallback"
    assert "BUY" in text or "BBCA" in text


def test_llm_no_signal_to_buy_rejected():
    report = build_cycle_report(
        trading_date="2026-09-14",
        mode="PAPER",
        pf_summary={"cash": 10_000_000, "equity": 10_000_000, "open_positions": {}},
        signal=None,
        no_signal_reasons=["no candidates"],
    )
    bad = "Decision: BUY BBCA now\nNO LIVE EXECUTION"
    report.signal = SignalReport(
        signal_id="ns",
        timestamp="t",
        symbol="",
        decision="NO_SIGNAL",
        confidence_method="none",
    )
    problems = validate_llm_output(bad, report)
    assert any("mutated_no_signal" in p for p in problems)


def test_signal_only_invariants_on_cycle():
    report = build_cycle_report(
        trading_date="2026-09-14",
        mode="PAPER",
        pf_summary={"cash": 10_000_000, "equity": 10_000_000, "open_positions": {}},
    )
    assert report.signal_only is True
    assert report.live_execution is False


def test_soak_1000_cycles_no_invalid_math():
    invalid = 0
    for i in range(1000):
        lots = 1 + (i % 10)
        entry = 1000 + (i % 50) * 10
        mark = entry + (i % 7)
        shares = shares_from_lots(lots)
        pv = position_value(entry, shares)
        if abs(shares - lots * 100) > 1e-9:
            invalid += 1
        if abs(pv - entry * shares) > 1e-6:
            invalid += 1
        upnl = unrealized_pnl_long(mark, entry, shares)
        if abs(upnl - (mark - entry) * shares) > 1e-6:
            invalid += 1
    assert invalid == 0
