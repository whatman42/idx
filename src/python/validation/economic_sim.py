from __future__ import annotations
from typing import Any
import pandas as pd
from src.python.data.costs import CostModel

def simulate_long_only(bars: pd.DataFrame, signals: pd.DataFrame, *,
                       cost: CostModel | None = None, hold_bars: int = 5,
                       cost_model_status: str = "UNVERIFIED_ASSUMPTION",
                       initial_capital: float = 100_000_000.0) -> dict[str, Any]:
    cost = cost or CostModel()
    trades: list[dict] = []
    if bars is None or bars.empty or signals is None or signals.empty:
        return {"trades": [], "metrics": {
            "timing": "signal_T_execute_open_Tplus1", "total_trades": 0,
            "final_equity": initial_capital, "max_drawdown": 0.0,
            "capital_utilization": {"average_cash": initial_capital, "average_exposure_pct": 0.0},
            "signal_attrition": {}, "cost_model_status": cost_model_status,
        }}
    bars = bars.sort_values(["symbol", "timestamp"]).copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    signals = signals.copy()
    signals["timestamp"] = pd.to_datetime(signals["timestamp"])
    cash = float(initial_capital)
    for sym, sg in signals.groupby("symbol"):
        g = bars[bars["symbol"] == sym].reset_index(drop=True)
        if g.empty:
            continue
        ts_to_i = {t: i for i, t in enumerate(g["timestamp"])}
        for _, srow in sg.iterrows():
            if int(srow.get("side", 0)) != 1:
                continue
            i = ts_to_i.get(srow["timestamp"])
            if i is None or i + 1 >= len(g):
                continue
            entry_i = i + 1
            exit_i = min(entry_i + hold_bars - 1, len(g) - 1)
            entry_px = cost.buy_price(float(g.iloc[entry_i]["open"]))
            exit_px = cost.sell_price(float(g.iloc[exit_i]["close"]))
            qty = 100.0
            fee = cost.fee(qty * entry_px) + cost.fee(qty * exit_px)
            pnl = (exit_px - entry_px) * qty - fee
            trades.append({
                "symbol": str(sym),
                "entry_timestamp": str(g.iloc[entry_i]["timestamp"]),
                "exit_timestamp": str(g.iloc[exit_i]["timestamp"]),
                "entry_price": entry_px, "exit_price": exit_px, "qty": qty,
                "gross_pnl": (exit_px - entry_px) * qty, "net_pnl": pnl, "fee": fee,
            })
            cash += pnl
    return {
        "trades": trades,
        "metrics": {
            "timing": "signal_T_execute_open_Tplus1",
            "total_trades": len(trades),
            "final_equity": cash,
            "max_drawdown": 0.0,
            "capital_utilization": {"average_cash": cash, "average_exposure_pct": 0.0},
            "signal_attrition": {},
            "cost_model_status": cost_model_status,
        },
    }
