from __future__ import annotations
import hashlib

def notification_id(*, trading_date: str, symbol: str, signal_type: str, model_version: str) -> str:
    raw = f"{trading_date}|{symbol}|{signal_type}|{model_version}"
    return "nid_" + hashlib.sha256(raw.encode()).hexdigest()[:20]

def format_signal_message(*, trading_date: str, signals: list[dict], portfolio: dict,
                          governor: str, dq: str, mode: str) -> str:
    lines = [f"\U0001F4CA IDX DAILY SIGNAL", f"Date: {trading_date}", f"Mode: {mode}", ""]
    for s in signals:
        lines.append(f"{s.get('symbol')} — {s.get('side_label', 'BUY')}")
        conf = s.get("confidence")
        if conf is not None:
            lines.append(f"Confidence: {float(conf)*100:.1f}%")
    lines += ["", "PAPER PORTFOLIO"]
    if portfolio.get("initial_capital") is not None:
        lines.append(f"Initial: Rp{portfolio['initial_capital']:,.0f}")
    if portfolio.get("equity") is not None:
        lines.append(f"Equity: Rp{float(portfolio['equity']):,.0f}")
    if portfolio.get("cash") is not None:
        lines.append(f"Cash: Rp{float(portfolio['cash']):,.0f}")
    if portfolio.get("exposure") is not None:
        lines.append(f"Exposure: {float(portfolio['exposure'])*100:.1f}%")
    lines += ["", f"Governor: {governor}", f"DQ: {dq}", "",
              "\u26A0\uFE0F SIGNAL ONLY", "Paper simulation \u2014 NO LIVE EXECUTION"]
    return "\n".join(lines)

def format_halt_message(*, reason: str, trading_date: str, details: str) -> str:
    return f"\u26A0\uFE0F IDX HALTED\n\n{reason}\nDate: {trading_date}\n{details}\n\nNo signal generated.\nPaper portfolio unchanged."
