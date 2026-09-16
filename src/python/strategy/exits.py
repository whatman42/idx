"""Adaptive exit plans — replace one-size-fits-all 3%/6% when ATR available."""
from __future__ import annotations

from typing import Optional

from src.python.strategy.contracts import ExitPlan, RegimeState


def build_exit_plan(
    *,
    entry_price: float,
    atr: Optional[float] = None,
    atr_sl_mult: float = 2.0,
    atr_tp_mult: float = 3.0,
    default_sl_pct: float = 0.03,
    default_tp_pct: float = 0.06,
    trailing_pct: Optional[float] = None,
    time_stop_bars: int = 5,
    regime: Optional[RegimeState] = None,
    max_adverse_excursion_pct: Optional[float] = None,
) -> ExitPlan:
    entry = float(entry_price) if entry_price else 0.0
    method = "static_pct"
    sl_pct = float(default_sl_pct)
    tp_pct = float(default_tp_pct)
    atr_sl = None
    atr_tp = None

    if atr is not None and entry > 0 and float(atr) > 0:
        atr_f = float(atr)
        sl_pct = (atr_f * atr_sl_mult) / entry
        tp_pct = (atr_f * atr_tp_mult) / entry
        atr_sl = atr_sl_mult
        atr_tp = atr_tp_mult
        method = "atr"
        # floor/ceil to avoid tiny or insane stops
        sl_pct = min(max(sl_pct, 0.01), 0.12)
        tp_pct = min(max(tp_pct, 0.02), 0.25)

    if regime is not None:
        if regime.volatility == "high":
            sl_pct *= 1.25
            tp_pct *= 1.15
            method = method + "+vol_widen"
        elif regime.volatility == "low":
            sl_pct *= 0.9
            method = method + "+vol_tighten"
        if regime.drawdown == "stress":
            time_stop_bars = min(time_stop_bars, 3)

    return ExitPlan(
        sl_pct=float(sl_pct),
        tp_pct=float(tp_pct),
        atr_sl_mult=atr_sl,
        atr_tp_mult=atr_tp,
        trailing_pct=trailing_pct,
        time_stop_bars=int(time_stop_bars),
        trend_break_exit=True,
        momentum_deterioration_exit=True,
        max_adverse_excursion_pct=max_adverse_excursion_pct,
        method=method,
    )
