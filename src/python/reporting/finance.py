"""Canonical IDX financial formulas. Shares are the base unit. 1 lot = 100 shares."""
from __future__ import annotations

SHARES_PER_LOT: int = 100


def shares_from_lots(lots: float) -> float:
    return float(lots) * SHARES_PER_LOT


def lots_from_shares(shares: float) -> float:
    return float(shares) / SHARES_PER_LOT


def position_value(entry_price: float, shares: float) -> float:
    return float(entry_price) * float(shares)


def exposure_pct(position_value_: float, equity: float) -> float:
    if equity <= 0:
        return 0.0
    return float(position_value_) / float(equity) * 100.0


def risk_amount(entry_price: float, stop_loss: float, shares: float) -> float:
    return abs(float(entry_price) - float(stop_loss)) * float(shares)


def risk_pct(risk_amount_: float, equity: float) -> float:
    if equity <= 0:
        return 0.0
    return float(risk_amount_) / float(equity) * 100.0


def reward_risk_ratio(entry: float, tp: float, sl: float) -> float | None:
    """Long RR = (tp - entry) / (entry - sl). None if risk <= 0."""
    risk = float(entry) - float(sl)
    if risk <= 0:
        return None
    reward = float(tp) - float(entry)
    return reward / risk


def unrealized_pnl_long(mark_price: float, entry_price: float, shares: float) -> float:
    return (float(mark_price) - float(entry_price)) * float(shares)


def realized_pnl_long(exit_price: float, entry_price: float, shares: float) -> float:
    return (float(exit_price) - float(entry_price)) * float(shares)


def round_lots_down(target_shares: float) -> float:
    """Round down to whole lots (multiples of 100 shares)."""
    if target_shares < SHARES_PER_LOT:
        return 0.0
    return float(int(target_shares // SHARES_PER_LOT) * SHARES_PER_LOT)
