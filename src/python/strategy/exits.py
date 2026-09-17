"""Adaptive exit plans — ATR-based when available; static 3%/6% fallback.

IDX daily swing defaults (ops paper path):
  - SL ≈ 1.8×ATR, TP ≈ 3.2×ATR  → target RRR ≈ 1.78 before clamps
  - Trailing ≈ 1.5×ATR as % of price (clamped 2%–6%)
  - Floors include fee/slippage buffer so micro-ATR names are not over-stopped
"""
from __future__ import annotations

from typing import Any, Optional

from src.python.strategy.contracts import ExitPlan, RegimeState

# --- Tunable defaults (single place) ---
ATR_SL_MULT = 1.8
ATR_TP_MULT = 3.2
ATR_TRAIL_MULT = 1.5
ATR_WINDOW = 14

# Absolute clamps on distance as fraction of entry (IDX daily)
SL_PCT_MIN = 0.015   # ≥1.5% — covers ~fee+slip round-trip buffer
SL_PCT_MAX = 0.08    # ≤8%  — avoid giant holes on thin names
TP_PCT_MIN = 0.03
TP_PCT_MAX = 0.18

TRAIL_PCT_MIN = 0.02
TRAIL_PCT_MAX = 0.06

MIN_RRR = 1.5         # enforce after clamps / regime adjust

STATIC_SL_PCT = 0.03
STATIC_TP_PCT = 0.06
DEFAULT_TIME_STOP_BARS = 8  # slightly longer for ATR trend path


def atr_exit_defaults() -> dict[str, Any]:
    """Expose current tunables for reports / audit."""
    return {
        "atr_sl_mult": ATR_SL_MULT,
        "atr_tp_mult": ATR_TP_MULT,
        "atr_trail_mult": ATR_TRAIL_MULT,
        "atr_window": ATR_WINDOW,
        "sl_pct_min": SL_PCT_MIN,
        "sl_pct_max": SL_PCT_MAX,
        "tp_pct_min": TP_PCT_MIN,
        "tp_pct_max": TP_PCT_MAX,
        "trail_pct_min": TRAIL_PCT_MIN,
        "trail_pct_max": TRAIL_PCT_MAX,
        "min_rrr": MIN_RRR,
        "static_sl_pct": STATIC_SL_PCT,
        "static_tp_pct": STATIC_TP_PCT,
        "default_time_stop_bars": DEFAULT_TIME_STOP_BARS,
        "version": "atr_opt_v1",
    }


def _clamp(x: float, lo: float, hi: float) -> float:
    return float(min(max(float(x), float(lo)), float(hi)))


def _enforce_min_rrr(sl_pct: float, tp_pct: float, min_rrr: float = MIN_RRR) -> tuple[float, float]:
    """If RRR too low after clamps, stretch TP (prefer reward) up to TP_PCT_MAX."""
    if sl_pct <= 0:
        return sl_pct, tp_pct
    rrr = tp_pct / sl_pct
    if rrr >= min_rrr:
        return sl_pct, tp_pct
    tp2 = min(sl_pct * min_rrr, TP_PCT_MAX)
    return sl_pct, float(tp2)


def trail_pct_from_atr(entry_price: float, atr: float, mult: float = ATR_TRAIL_MULT) -> float:
    """Trailing distance as fraction of price: mult×ATR/entry, clamped."""
    entry = float(entry_price)
    if entry <= 0 or atr is None or float(atr) <= 0:
        return TRAIL_PCT_MIN
    raw = (float(atr) * float(mult)) / entry
    return _clamp(raw, TRAIL_PCT_MIN, TRAIL_PCT_MAX)


def build_exit_plan(
    *,
    entry_price: float,
    atr: Optional[float] = None,
    atr_sl_mult: float = ATR_SL_MULT,
    atr_tp_mult: float = ATR_TP_MULT,
    default_sl_pct: float = STATIC_SL_PCT,
    default_tp_pct: float = STATIC_TP_PCT,
    trailing_pct: Optional[float] = None,
    time_stop_bars: int = DEFAULT_TIME_STOP_BARS,
    regime: Optional[RegimeState] = None,
    max_adverse_excursion_pct: Optional[float] = None,
) -> ExitPlan:
    entry = float(entry_price) if entry_price else 0.0
    method = "static_pct"
    sl_pct = float(default_sl_pct)
    tp_pct = float(default_tp_pct)
    atr_sl = None
    atr_tp = None
    trail = trailing_pct

    if atr is not None and entry > 0 and float(atr) > 0:
        atr_f = float(atr)
        sl_pct = (atr_f * float(atr_sl_mult)) / entry
        tp_pct = (atr_f * float(atr_tp_mult)) / entry
        atr_sl = float(atr_sl_mult)
        atr_tp = float(atr_tp_mult)
        method = "atr"
        sl_pct = _clamp(sl_pct, SL_PCT_MIN, SL_PCT_MAX)
        tp_pct = _clamp(tp_pct, TP_PCT_MIN, TP_PCT_MAX)
        if trail is None:
            trail = trail_pct_from_atr(entry, atr_f, ATR_TRAIL_MULT)

    if regime is not None:
        if regime.volatility == "high":
            sl_pct *= 1.20
            tp_pct *= 1.10
            method = method + "+vol_widen"
        elif regime.volatility == "low":
            sl_pct *= 0.92
            method = method + "+vol_tighten"
        if regime.drawdown == "stress":
            time_stop_bars = min(int(time_stop_bars), 4)
            method = method + "+stress_shorten"

        # re-clamp after regime scale
        if method.startswith("atr"):
            sl_pct = _clamp(sl_pct, SL_PCT_MIN, SL_PCT_MAX)
            tp_pct = _clamp(tp_pct, TP_PCT_MIN, TP_PCT_MAX)

    sl_pct, tp_pct = _enforce_min_rrr(sl_pct, tp_pct, MIN_RRR)

    if trail is not None:
        trail = _clamp(float(trail), TRAIL_PCT_MIN, TRAIL_PCT_MAX)

    return ExitPlan(
        sl_pct=float(sl_pct),
        tp_pct=float(tp_pct),
        atr_sl_mult=atr_sl,
        atr_tp_mult=atr_tp,
        trailing_pct=trail,
        time_stop_bars=int(time_stop_bars),
        trend_break_exit=True,
        momentum_deterioration_exit=True,
        max_adverse_excursion_pct=max_adverse_excursion_pct,
        method=method,
    )
