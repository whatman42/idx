"""Fail-closed validation for structured reports before Telegram delivery."""
from __future__ import annotations

from typing import Any, Optional

from src.python.reporting.finance import (
    SHARES_PER_LOT,
    exposure_pct,
    lots_from_shares,
    position_value,
    risk_amount,
    shares_from_lots,
    unrealized_pnl_long,
)
from src.python.reporting.models import (
    CycleReport,
    ExitReport,
    OpenPositionView,
    PortfolioSnapshot,
    SignalReport,
)

_MONEY_EPS = 1.0
_PCT_EPS = 0.05


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def validate_position_math(
    *,
    entry_price: float,
    mark_price: float,
    shares: float,
    lots: float,
    market_value: float,
    unrealized_pnl: float,
    stop_loss: float = 0.0,
    risk_amount_: Optional[float] = None,
    equity: Optional[float] = None,
) -> list[str]:
    errs: list[str] = []
    expected_shares = shares_from_lots(lots) if lots else shares
    if abs(shares - expected_shares) > 1e-6 and lots:
        errs.append(f"shares_lots_mismatch shares={shares} lots={lots} expected_shares={expected_shares}")
    if abs(lots_from_shares(shares) - lots) > 1e-6 and shares:
        errs.append(f"lots_from_shares_mismatch lots={lots} from_shares={lots_from_shares(shares)}")
    if entry_price > 0 and shares > 0 and mark_price > 0:
        mark_mv = position_value(mark_price, shares)
        if market_value > 0 and abs(market_value - mark_mv) > _MONEY_EPS:
            errs.append(f"market_value_mismatch got={market_value} mark_mv={mark_mv}")
        exp_upnl = unrealized_pnl_long(mark_price, entry_price, shares)
        if abs(unrealized_pnl - exp_upnl) > _MONEY_EPS:
            errs.append(f"upnl_mismatch got={unrealized_pnl} expected={exp_upnl}")
    if lots >= 1 and shares > 0 and abs(shares - lots) < 1e-6:
        errs.append(f"shares_equals_lots_bug lots={lots} shares={shares} (1 lot must be {SHARES_PER_LOT} shares)")
    if risk_amount_ is not None and equity and stop_loss > 0 and shares > 0:
        exp_risk = risk_amount(entry_price, stop_loss, shares)
        if abs(risk_amount_ - exp_risk) > _MONEY_EPS:
            errs.append(f"risk_amount_mismatch got={risk_amount_} expected={exp_risk}")
    return errs


def validate_portfolio_math(snap: PortfolioSnapshot) -> list[str]:
    errs: list[str] = []
    sum_mv = sum(float(p.market_value) for p in snap.open_positions)
    sum_upnl = sum(float(p.unrealized_pnl) for p in snap.open_positions)
    if abs(sum_mv - float(snap.market_value)) > _MONEY_EPS:
        errs.append(f"portfolio_mv_mismatch sum_pos={sum_mv} snap={snap.market_value}")
    if abs(sum_upnl - float(snap.unrealized_pnl)) > _MONEY_EPS:
        errs.append(f"portfolio_upnl_mismatch sum_pos={sum_upnl} snap={snap.unrealized_pnl}")
    recon = float(snap.cash) + float(snap.market_value)
    if abs(recon - float(snap.equity)) > _MONEY_EPS:
        errs.append(f"equity_recon_mismatch cash+mv={recon} equity={snap.equity}")
    if float(snap.equity) > 0:
        exp_exp = exposure_pct(float(snap.market_value), float(snap.equity))
        if abs(exp_exp - float(snap.exposure_pct)) > _PCT_EPS:
            errs.append(f"exposure_mismatch got={snap.exposure_pct} expected={exp_exp}")
    for p in snap.open_positions:
        errs.extend(
            validate_position_math(
                entry_price=p.entry_price,
                mark_price=p.mark_price,
                shares=p.shares,
                lots=p.lots,
                market_value=p.market_value,
                unrealized_pnl=p.unrealized_pnl,
                stop_loss=p.stop_loss,
            )
        )
    return errs


def validate_exit_report(ex: ExitReport) -> list[str]:
    errs: list[str] = []
    if not ex.symbol:
        errs.append("exit_missing_symbol")
    if ex.shares <= 0:
        errs.append("exit_invalid_shares")
    if abs(shares_from_lots(ex.lots) - ex.shares) > 1e-6 and ex.lots:
        errs.append(f"exit_shares_lots_mismatch shares={ex.shares} lots={ex.lots}")
    if not ex.exit_reason:
        errs.append("exit_missing_reason")
    if not ex.timestamp:
        errs.append("exit_missing_timestamp")
    if ex.shares > 0 and ex.entry_price > 0 and ex.exit_price > 0:
        from src.python.reporting.finance import realized_pnl_long
        exp = realized_pnl_long(ex.exit_price, ex.entry_price, ex.shares)
        if abs(exp - ex.realized_pnl) > _MONEY_EPS:
            errs.append(f"exit_pnl_mismatch got={ex.realized_pnl} expected={exp}")
    return errs


def validate_signal_report(sig: SignalReport) -> list[str]:
    errs: list[str] = []
    if sig.decision not in ("BUY", "SELL", "NO_SIGNAL"):
        errs.append(f"invalid_decision={sig.decision}")
    if not sig.signal_id:
        errs.append("missing_signal_id")
    if sig.decision in ("BUY", "SELL"):
        if not sig.symbol:
            errs.append("missing_symbol")
        if sig.entry_reference <= 0:
            errs.append("invalid_entry_reference")
        if sig.shares < 0 or sig.lots < 0:
            errs.append("negative_size")
        if sig.lots > 0 and abs(shares_from_lots(sig.lots) - sig.shares) > 1e-6:
            errs.append(f"signal_shares_lots_mismatch shares={sig.shares} lots={sig.lots}")
        if sig.shares > 0 and sig.entry_reference > 0:
            exp_pv = position_value(sig.entry_reference, sig.shares)
            if abs(exp_pv - sig.position_value) > _MONEY_EPS:
                errs.append(f"signal_position_value_mismatch got={sig.position_value} expected={exp_pv}")
        if sig.stop_loss > 0 and sig.shares > 0 and sig.entry_reference > 0:
            exp_risk = risk_amount(sig.entry_reference, sig.stop_loss, sig.shares)
            if abs(exp_risk - sig.risk_amount) > _MONEY_EPS:
                errs.append(f"signal_risk_mismatch got={sig.risk_amount} expected={exp_risk}")
        if sig.lots >= 5 and abs(sig.shares - 50) < 1e-6:
            errs.append("regression_bug_50_shares_for_5_lots")
        if sig.lots >= 5 and sig.entry_reference >= 9800 and abs(sig.position_value - 492_500) < 1.0:
            errs.append("regression_bug_492500_notional_for_5_lots")
    if sig.confidence < 0 or sig.confidence > 100:
        errs.append(f"confidence_out_of_range={sig.confidence}")
    if not sig.confidence_method:
        errs.append("missing_confidence_method")
    return errs


def validate_cycle_report(report: CycleReport) -> list[str]:
    errs: list[str] = []
    if not report.signal_only:
        errs.append("signal_only_must_be_true")
    if report.live_execution:
        errs.append("live_execution_must_be_false")
    if report.signal:
        errs.extend(validate_signal_report(report.signal))
    if report.portfolio:
        errs.extend(validate_portfolio_math(report.portfolio))
    for ex in report.exits:
        errs.extend(validate_exit_report(ex))
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
    return errs
