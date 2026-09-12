"""Cost sensitivity grid — always labels cost_model_status honestly."""
from __future__ import annotations

from typing import Any
import pandas as pd
from src.python.data.costs import CostModel
from src.python.validation.economic_sim import simulate_long_only


def cost_grid(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    fee_bps_list: list[float] | None = None,
    slippage_bps_list: list[float] | None = None,
    hold_bars: int = 5,
    initial_capital: float = 10_000_000.0,
) -> dict[str, Any]:
    fee_bps_list = fee_bps_list or [0.0, 10.0, 15.0, 25.0, 40.0]
    slippage_bps_list = slippage_bps_list or [0.0, 5.0, 10.0, 20.0]
    results = []
    for fee in fee_bps_list:
        for slip in slippage_bps_list:
            sim = simulate_long_only(
                bars, signals,
                cost=CostModel(fee_bps=fee, slippage_bps=slip),
                hold_bars=hold_bars,
                cost_model_status="UNVERIFIED_ASSUMPTION",
                initial_capital=initial_capital,
            )
            m = sim.get("metrics") or {}
            final_eq = float(m.get("final_equity", initial_capital))
            results.append({
                "fee_bps": fee,
                "slippage_bps": slip,
                "total_trades": m.get("total_trades", 0),
                "final_equity": final_eq,
                "net_pnl": final_eq - initial_capital,
                "cost_model_status": "UNVERIFIED_ASSUMPTION",
            })
    positive = [r for r in results if r["net_pnl"] > 0]
    return {
        "grid": results,
        "any_positive_net": len(positive) > 0,
        "all_positive_net": len(positive) == len(results) and len(results) > 0,
        "edge_status": "COST_SENSITIVE_OR_UNVERIFIED",
        "cost_model_status": "UNVERIFIED_ASSUMPTION",
        "note": "Positive cells do NOT equal verified edge; costs are assumptions.",
    }
