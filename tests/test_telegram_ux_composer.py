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
    # Canonical funds labels (composer contract)
    assert "Modal Awal" in text
    assert "Total Equity" in text
    assert "Dana Tunai" in text
    assert "Dana Terpakai" in text
    assert "Total P/L" in text
    assert "TIDAK ADA PEMBELIAN" in text
    assert "Tidak ada posisi aktif" in text
    assert "Pertahankan dana dalam bentuk kas" in text or "Tidak ada pembelian baru" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text or "MODE OPERASI" in text
    assert "PAPER TRADING" in text or "INSTANT SIMULATION" in text
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
        confidence_method="sma20",
        explanation=["Ranking #1 universe filter"],
        fill_status="FULL_FILL",
    )
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary={
            "cash": 5_195_000,
            "equity": 10_145_000,
            "realized_pnl": 0,
            "unrealized_pnl": 25_000,
            "initial_capital": 10_000_000,
            "exposure_pct": 48.0,
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
    assert "PORTOFOLIO SAHAM IDX" in text
    assert "Modal Awal" in text
    assert "BBCA" in text
    assert "PAPER FILL" in text or "FILLED" in text or "BUY" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text or "MODE OPERASI" in text
    assert "NO LIVE EXECUTION" in text


def test_integrity_failure_blocks_signal_language():
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary=_empty_pf(),
        status="BLOCKED",
        integrity_ok=False,
        integrity_errors=["ledger_mismatch"],
    )
    text = compose_telegram_message(report)
    assert "DATA TIDAK VALID" in text or "BLOCKED" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text or "MODE OPERASI" in text


def test_mode_label_paper_simulation():
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary=_empty_pf(),
        status="NO_SIGNAL",
        no_signal_reasons=["x"],
    )
    text = compose_telegram_message(report)
    assert "PAPER" in text
    assert "INSTANT SIMULATION" in text or "PAPER TRADING" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text or "MODE OPERASI" in text


def test_no_marketing_guarantees():
    report = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary=_empty_pf(),
        status="NO_SIGNAL",
        no_signal_reasons=["x"],
    )
    text = compose_telegram_message(report).upper()
    for banned in ("PASTI UNTUNG", "INVESTASI AMAN", "SANGAT AMAN", "RISIKO TERKENDALI"):
        assert banned not in text
    assert "NO LIVE EXECUTION" in text or "SIGNAL ONLY" in text or "MODE OPERASI" in text


def test_empty_report_still_safe():
    report = CycleReport(
        trading_date="2026-09-15",
        mode="PAPER",
        status="NO_SIGNAL",
        integrity_ok=True,
        live_execution=False,
    )
    text = compose_telegram_message(report)
    assert "PORTOFOLIO SAHAM IDX" in text
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text or "MODE OPERASI" in text
