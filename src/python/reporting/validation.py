"""Fail-closed validation for structured reports before Telegram delivery."""
from __future__ import annotations

from typing import Any, Optional

from src.python.reporting.models import (
    CycleReport,
    PortfolioSnapshot,
    SignalReport,
)


def _num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def validate_portfolio_snapshot(snap: PortfolioSnapshot) -> list[str]:
    errs: list[str] = []
    if snap is None:
        return ["missing_portfolio"]
    equity = _num(snap.equity)
    cash = _num(snap.cash)
    mv = _num(snap.market_value)
    if equity is None or cash is None:
        errs.append("missing_equity_or_cash")
        return errs
    sum_mv = sum(float(p.market_value or 0) for p in (snap.open_positions or []))
    sum_upnl = sum(float(p.unrealized_pnl or 0) for p in (snap.open_positions or []))
    if mv is not None and abs(sum_mv - mv) > 2.0:
        errs.append("market_value_mismatch")
    if abs((cash + (mv if mv is not None else sum_mv)) - equity) > 5.0:
        errs.append("equity_ne_cash_plus_mv")
    for p in snap.open_positions or []:
        if not p.symbol:
            errs.append("position_missing_symbol")
    return errs


def validate_cycle_report(report: CycleReport) -> list[str]:
    errs: list[str] = []
    if report is None:
        return ["missing_report"]
    if report.live_execution:
        errs.append("live_execution_true")
    if report.portfolio:
        errs.extend(validate_portfolio_snapshot(report.portfolio))
    return errs


def validate_telegram_payload(text: str, report: CycleReport) -> list[str]:
    errs: list[str] = []
    if not text or not text.strip():
        return ["empty_telegram_text"]
    if "NO LIVE EXECUTION" not in text and "SIGNAL ONLY" not in text and "SIGNAL_ONLY" not in text:
        errs.append("missing_signal_only_disclaimer")
    if report.live_execution:
        errs.append("payload_claims_live")
    sig = report.signal
    if sig and sig.decision == "BUY" and sig.symbol:
        if sig.symbol not in text:
            errs.append(f"missing_symbol_in_text={sig.symbol}")
        fill = str(getattr(sig, "fill_status", "") or "")
        claimed = f"ASET PORTOFOLIO: {sig.symbol} tercatat" in text
        if claimed and (
            fill.startswith("SKIPPED")
            or fill.startswith("REJECTED")
            or fill.startswith("BLOCKED")
            or fill in ("", "NO_FILL")
        ):
            errs.append("skipped_claimed_as_position")
        if claimed and fill in ("PAPER_FILLED", "FULL_FILL", "FILLED"):
            pf = report.portfolio
            open_syms = {
                str(getattr(op, "symbol", "") or "")
                for op in (getattr(pf, "open_positions", None) or [])
            }
            if sig.symbol not in open_syms:
                errs.append("filled_claim_but_not_in_portfolio_ssot")
    return errs
