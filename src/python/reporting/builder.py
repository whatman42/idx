"""Build CycleReport from paper portfolio + signal payloads (no Telegram math)."""
from __future__ import annotations

from typing import Any, Optional

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
)
from src.python.reporting.models import (
    CycleReport,
    ExitReport,
    OpenPositionView,
    PortfolioSnapshot,
    SignalReport,
)
from src.python.reporting.validation import validate_cycle_report


def build_open_position(
    *,
    symbol: str,
    entry_price: float,
    mark_price: float,
    shares: float,
    tp: float = 0.0,
    sl: float = 0.0,
    opened_at: str = "",
    signal_id: str = "",
    tp1: float = 0.0,
) -> OpenPositionView:
    lots = lots_from_shares(shares)
    mark = mark_price or entry_price
    mv = position_value(mark, shares)
    upnl = unrealized_pnl_long(mark, entry_price, shares)
    return OpenPositionView(
        symbol=symbol,
        entry_price=float(entry_price),
        mark_price=float(mark),
        shares=float(shares),
        lots=float(lots),
        market_value=float(mv),
        unrealized_pnl=float(upnl),
        tp1=float(tp1 or 0.0),
        tp2=float(tp or 0.0),
        stop_loss=float(sl or 0.0),
        opened_at=opened_at,
        duration="Not configured",
        signal_id=signal_id,
    )


def build_portfolio_snapshot(pf_summary: dict[str, Any], marks: Optional[dict[str, float]] = None) -> PortfolioSnapshot:
    marks = marks or {}
    open_raw = pf_summary.get("open_positions") or {}
    positions: list[OpenPositionView] = []
    for sym, p in open_raw.items():
        if not isinstance(p, dict):
            continue
        entry = float(p.get("avg_entry") or p.get("entry_price") or 0)
        mark = float(p.get("last_mark") or marks.get(sym) or entry)
        qty = float(p.get("qty") or p.get("shares") or 0)
        if qty <= 0 and p.get("lots"):
            qty = shares_from_lots(float(p["lots"]))
        lots = float(p.get("lots") or lots_from_shares(qty))
        shares = qty
        if shares > 0 and shares < SHARES_PER_LOT and abs(lots - shares) < 1e-9:
            shares = shares_from_lots(shares)
            lots = lots_from_shares(shares)
        positions.append(
            build_open_position(
                symbol=str(sym),
                entry_price=entry,
                mark_price=mark,
                shares=shares,
                tp=float(p.get("tp") or 0),
                sl=float(p.get("sl") or 0),
                opened_at=str(p.get("entry_timestamp") or ""),
                signal_id=str(p.get("signal_id") or ""),
            )
        )
    market_value = sum(p.market_value for p in positions)
    cash = float(pf_summary.get("cash") or 0)
    equity = float(pf_summary.get("equity") or (cash + market_value))
    unrealized = sum(p.unrealized_pnl for p in positions)
    realized = float(pf_summary.get("realized_pnl") or 0)
    exp = exposure_pct(market_value, equity) if equity else 0.0
    return PortfolioSnapshot(
        equity=equity,
        cash=cash,
        market_value=market_value,
        exposure_pct=exp,
        realized_pnl=realized,
        unrealized_pnl=unrealized,
        open_positions=positions,
        initial_capital=float(pf_summary.get("initial_capital") or 0),
        simulation_session_id=str(pf_summary.get("simulation_session_id") or ""),
        last_event=str(pf_summary.get("last_event") or ""),
    )


def build_exit_from_trade(trade: dict[str, Any]) -> Optional[ExitReport]:
    if not trade:
        return None
    if trade.get("action") not in ("SELL", "EXIT") and trade.get("side") not in (-1, "SELL"):
        if not trade.get("exit_reason") and not trade.get("reason"):
            if trade.get("action") != "SELL" and trade.get("side") != -1:
                return None
    symbol = str(trade.get("symbol") or "")
    entry = float(trade.get("entry") or trade.get("entry_price") or 0)
    exit_px = float(trade.get("price") or trade.get("exit_price") or 0)
    shares = float(trade.get("qty") or trade.get("shares") or 0)
    lots = float(trade.get("lots") or lots_from_shares(shares))
    if shares <= 0 and lots > 0:
        shares = shares_from_lots(lots)
    pnl = float(trade.get("pnl") or trade.get("realized_pnl") or 0)
    pnl_pct = 0.0
    if entry > 0 and shares > 0:
        pnl_pct = (pnl / (entry * shares)) * 100.0
    return ExitReport(
        symbol=symbol,
        entry_price=entry,
        exit_price=exit_px,
        shares=shares,
        lots=lots,
        realized_pnl=pnl,
        pnl_pct=pnl_pct,
        duration=str(trade.get("duration") or "Not configured"),
        exit_reason=str(trade.get("reason") or trade.get("exit_reason") or "UNKNOWN"),
        timestamp=str(trade.get("timestamp") or ""),
        signal_id=str(trade.get("signal_id") or ""),
    )


def build_buy_signal(
    *,
    signal_id: str,
    timestamp: str,
    symbol: str,
    entry_reference: float,
    stop_loss: float,
    tp1: float,
    tp2: float,
    shares: float,
    equity: float,
    confidence: float,
    confidence_method: str,
    model_version: str = "",
    feature_version: str = "",
    explanation: Optional[list[str]] = None,
    timeframe: str = "Swing 5–20 hari",
    market_regime: str = "Unknown",
    entry_low: float = 0.0,
    entry_high: float = 0.0,
    fill_status: str = "",
) -> SignalReport:
    lots = lots_from_shares(shares)
    pv = position_value(entry_reference, shares)
    alloc = (pv / equity * 100.0) if equity > 0 else 0.0
    ra = risk_amount(entry_reference, stop_loss, shares) if stop_loss > 0 else 0.0
    rp = risk_pct(ra, equity) if equity > 0 else 0.0
    conf = float(confidence)
    if conf <= 1.0:
        conf = conf * 100.0
    return SignalReport(
        signal_id=signal_id,
        timestamp=timestamp,
        symbol=symbol,
        decision="BUY",
        timeframe=timeframe,
        market_regime=market_regime,
        entry_reference=float(entry_reference),
        entry_low=float(entry_low or entry_reference),
        entry_high=float(entry_high or entry_reference),
        stop_loss=float(stop_loss),
        tp1=float(tp1),
        tp2=float(tp2),
        shares=float(shares),
        lots=float(lots),
        position_value=float(pv),
        allocation_pct=float(alloc),
        risk_amount=float(ra),
        risk_pct=float(rp),
        rr_tp1=reward_risk_ratio(entry_reference, tp1, stop_loss) if tp1 else None,
        rr_tp2=reward_risk_ratio(entry_reference, tp2, stop_loss) if tp2 else None,
        confidence=conf,
        confidence_method=confidence_method,
        explanation_context=list(explanation or ["Data tidak tersedia"]),
        model_version=model_version,
        feature_version=feature_version,
        management=["Not configured"],
        fill_status=fill_status,
    )


def build_cycle_report(
    *,
    trading_date: str,
    mode: str,
    pf_summary: dict[str, Any],
    signal: Optional[SignalReport] = None,
    exits: Optional[list[dict[str, Any]]] = None,
    marks: Optional[dict[str, float]] = None,
    model_version: str = "",
    governor_action: str = "",
    dq_status: str = "",
    data_source: str = "",
    no_signal_reasons: Optional[list[str]] = None,
    risk_gate: str = "PASS",
    status: str = "SUCCESS",
    signals_received: int = 0,
    signals_filled: int = 0,
    filled_symbols: Optional[list[str]] = None,
) -> CycleReport:
    portfolio = build_portfolio_snapshot(pf_summary, marks)
    exit_reports: list[ExitReport] = []
    for t in exits or []:
        er = build_exit_from_trade(t)
        if er:
            exit_reports.append(er)
    report = CycleReport(
        trading_date=trading_date,
        mode=mode,
        signal_only=True,
        live_execution=False,
        signal=signal,
        portfolio=portfolio,
        exits=exit_reports,
        status=status,
        governor_action=governor_action,
        dq_status=dq_status,
        data_source=data_source,
        model_version=model_version,
        no_signal_reasons=list(no_signal_reasons or []),
        risk_gate=risk_gate,
        signals_received=int(signals_received or 0),
        signals_filled=int(signals_filled or 0),
        filled_symbols=list(filled_symbols or []),
    )
    errs = validate_cycle_report(report)
    if errs:
        report.integrity_ok = False
        report.integrity_errors = errs
        report.status = "INTEGRITY_FAILURE"
    else:
        report.integrity_ok = True
        report.integrity_errors = []
    return report
