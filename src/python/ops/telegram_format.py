from __future__ import annotations
import hashlib
from typing import Any, Optional


def notification_id(*, trading_date: str, symbol: str, signal_type: str, model_version: str) -> str:
    raw = f"{trading_date}|{symbol}|{signal_type}|{model_version}"
    return "nid_" + hashlib.sha256(raw.encode()).hexdigest()[:20]


def _rp(x: Any) -> str:
    try:
        return f"Rp{float(x):,.0f}"
    except Exception:
        return "-"


def format_signal_message(
    *,
    trading_date: str,
    signals: list[dict],
    portfolio: dict,
    governor: str,
    dq: str,
    mode: str,
    exits: Optional[list[dict]] = None,
) -> str:
    lines = ["📊 IDX PORTFOLIO DASHBOARD", f"Date: {trading_date}", f"Mode: {mode}", ""]
    top = signals[0] if signals else None
    if top:
        lines += [
            "🎯 SINYAL TOP-1 (BUY)",
            f"  {top.get('symbol')} @ {_rp(top.get('price') or top.get('entry_price'))}",
            f"  Lot: {top.get('lots', '-')} | Total: {_rp(top.get('notional') or top.get('total_cost'))}",
            f"  TP: {_rp(top.get('tp'))} | SL: {_rp(top.get('sl'))}",
        ]
        conf = top.get("confidence")
        if conf is not None:
            lines.append(f"  Confidence: {float(conf)*100:.1f}%")
        if top.get("why"):
            lines.append(f"  Why: {top.get('why')}")
        lines.append("")
    if exits:
        lines.append("✅ EXIT HARI INI")
        for e in exits:
            lines.append(f"  {e.get('symbol')} {e.get('reason')} PnL {_rp(e.get('pnl'))}")
        lines.append("")
    lines += [
        "💼 PORTFOLIO",
        f"  Equity: {_rp(portfolio.get('equity'))}",
        f"  Cash: {_rp(portfolio.get('cash'))}",
    ]
    if portfolio.get("exposure") is not None:
        lines.append(f"  Exposure: {float(portfolio['exposure'])*100:.1f}%")
    if portfolio.get("realized_pnl") is not None:
        lines.append(f"  Realized: {_rp(portfolio.get('realized_pnl'))}")
    if portfolio.get("unrealized_pnl") is not None:
        lines.append(f"  Unrealized: {_rp(portfolio.get('unrealized_pnl'))}")
    lines.append("")
    opens = portfolio.get("open_positions") or {}
    if opens:
        lines.append("📦 POSISI TERBUKA")
        for sym, p in list(opens.items())[:15]:
            if isinstance(p, dict):
                lines.append(
                    f"  {sym} {float(p.get('lots') or 0):.0f} lot | "
                    f"entry {_rp(p.get('avg_entry'))} | mark {_rp(p.get('last_mark'))} | "
                    f"uPnL {_rp(p.get('unrealized_pnl'))} | TP {_rp(p.get('tp'))} SL {_rp(p.get('sl'))}"
                )
            else:
                lines.append(f"  {sym}")
        lines.append("")
    lines += [
        f"Governor: {governor}", f"DQ: {dq}", "",
        "⚠️ SIGNAL ONLY", "Paper simulation — NO LIVE EXECUTION",
    ]
    return "\n".join(lines)


def format_halt_message(*, reason: str, trading_date: str, details: str) -> str:
    return (
        f"⚠️ IDX HALTED\n\n{reason}\nDate: {trading_date}\n{details}\n\n"
        "No signal generated.\nPaper portfolio unchanged."
    )
