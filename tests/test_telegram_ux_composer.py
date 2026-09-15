"""Beginner-friendly Telegram dashboard UX — presentation only."""
from __future__ import annotations

from src.python.reporting.builder import (
    build_buy_signal,
    build_cycle_report,
)
from src.python.reporting.composer import compose_telegram_message
from src.python.reporting.models import CycleReport


def _empty_pf(**kwargs):
    base = {
        "cash": 10_000_000,
        "equity": 10_000_000,
        "realized_pnl": 0,
        "open_positions": {},
        "initial_capital": 10_000_000,
    }
    base.update(kwargs)
    return base


def test_no_position_no_signal_beginner_ux():
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary=_empty_pf(),
        no_signal_reasons=["Tidak ada saham yang memenuhi seluruh syarat pembelian saat ini."],
        status="NO_SIGNAL",
    )
    text = compose_telegram_message(report)
    assert "PORTOFOLIO SAHAM IDX" in text
    assert "KONDISI DANA" in text
    assert "Total Dana" in text
    assert "Dana Tunai" in text
    assert "Dana Terpakai" in text
    assert "Keuntungan/Rugi" in text
    assert "TIDAK ADA PEMBELIAN" in text
    assert "Tidak ada posisi aktif" in text
    assert "Pertahankan dana dalam bentuk kas" in text or "Tidak ada pembelian baru" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text
    assert "TOP 3" not in text
    assert "Exposure" not in text
    assert "volatilitas tinggi" not in text.lower()


def test_with_position_buy_signal():
    sig = build_buy_signal(
        signal_id="sig1",
        timestamp="2026-09-15",
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
        explanation=["Ranking #1 vs SMA20"],
        entry_low=9800,
        entry_high=9875,
        fill_status="FULL_FILL",
    )
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary={
            "cash": 5_195_000,
            "equity": 10_145_000,
            "realized_pnl": 0,
            "initial_capital": 10_000_000,
            "open_positions": {
                "BBCA": {
                    "avg_entry": 9850,
                    "last_mark": 9900,
                    "qty": 500,
                    "lots": 5,
                    "tp": 10441,
                    "sl": 9555,
                    "entry_timestamp": "2026-09-14",
                }
            },
        },
        signal=sig,
        model_version="ops_sma_v0",
    )
    text = compose_telegram_message(report)
    assert "BUY" in text and "BBCA" in text
    assert "Target Profit" in text
    assert "Batas Rugi" in text
    assert "Saham Dimiliki" in text
    assert "Model confidence: 72/100" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text
    assert report.integrity_ok


def test_sell_exit_rendering():
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary=_empty_pf(realized_pnl=90_000, equity=10_090_000, cash=10_090_000),
        exits=[
            {
                "symbol": "TLKM",
                "entry": 3800,
                "price": 3890,
                "qty": 1000,
                "lots": 10,
                "pnl": 90_000,
                "reason": "TP_HIT",
                "timestamp": "2026-09-15",
                "action": "SELL",
                "side": -1,
            }
        ],
        no_signal_reasons=["Tidak ada kandidat BUY baru."],
    )
    text = compose_telegram_message(report)
    assert "TLKM" in text
    assert "TP_HIT" in text or "EXIT" in text or "TRANSAKSI SELESAI" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text


def test_blocked_integrity_message():
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary=_empty_pf(),
    )
    report.integrity_ok = False
    report.integrity_errors = ["equity_recon_mismatch cash+mv=1 equity=2"]
    text = compose_telegram_message(report)
    assert "BLOCKED" in text or "DATA TIDAK VALID" in text
    assert "equity_recon_mismatch" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text


def test_risk_gate_blocked_status():
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary=_empty_pf(),
        risk_gate="BLOCKED",
        status="BLOCKED_RISK",
        no_signal_reasons=["Risk gate menolak sinyal."],
    )
    text = compose_telegram_message(report)
    assert "BLOCKED" in text
    assert "Risk gate" in text


def test_mode_never_claims_live_when_false():
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="OPERATIONAL",
        pf_summary=_empty_pf(),
    )
    assert report.live_execution is False
    text = compose_telegram_message(report)
    assert "NO LIVE EXECUTION" in text or "SIGNAL ONLY" in text
    assert "• LIVE" not in text or report.live_execution


def test_missing_portfolio_shows_unavailable():
    report = CycleReport(
        trading_date="2026-09-15",
        mode="PAPER",
        signal_only=True,
        live_execution=False,
        portfolio=None,
        no_signal_reasons=["Data portofolio tidak tersedia."],
    )
    text = compose_telegram_message(report)
    assert "Tidak tersedia" in text or "TIDAK ADA PEMBELIAN" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text


def test_rupiah_formatting_uses_dot_thousands():
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary=_empty_pf(equity=10_000_000, cash=10_000_000),
    )
    text = compose_telegram_message(report)
    assert "Rp10.000.000" in text


def test_bbca_regression_still_in_text():
    sig = build_buy_signal(
        signal_id="sig_bbca",
        timestamp="2026-09-15",
        symbol="BBCA",
        entry_reference=9850,
        stop_loss=9555,
        tp1=10150,
        tp2=10441,
        shares=500,
        equity=10_120_000,
        confidence=72,
        confidence_method="sma20_rank_score",
        explanation=["Ranking #1"],
    )
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary={
            "cash": 5_195_000,
            "equity": 10_145_000,
            "realized_pnl": 0,
            "initial_capital": 10_000_000,
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
    )
    text = compose_telegram_message(report)
    assert "500" in text
    assert "Model confidence: 72/100" in text
    assert "4.925.000" in text or "4925000" in text.replace(".", "")
