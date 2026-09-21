"""Tick size, lot, ARA/ARB validation — fail-closed if rules missing when required."""
from __future__ import annotations

from typing import Optional, Tuple

from src.python.market_structure.models import BlockReason, OrderRequest, PriceRules


def price_on_tick(price: float, tick: float, *, tol: float = 1e-9) -> bool:
    if tick <= 0:
        return False
    n = round(price / tick)
    return abs(price - n * tick) <= tol * max(1.0, abs(price))


def validate_quantity(qty: int, lot: int) -> Tuple[bool, BlockReason, str]:
    if qty <= 0:
        return False, BlockReason.INVALID_QUANTITY, "qty<=0"
    if lot <= 0:
        return False, BlockReason.INVALID_LOT, "lot_size invalid"
    if qty % lot != 0:
        return False, BlockReason.INVALID_LOT, f"qty {qty} not multiple of lot {lot}"
    return True, BlockReason.NONE, "ok"


def validate_price(
    price: float,
    rules: Optional[PriceRules],
    *,
    require_rules: bool = True,
) -> Tuple[bool, BlockReason, str]:
    if rules is None:
        if require_rules:
            return False, BlockReason.MISSING_PRICE_RULES, "no PriceRules"
        return True, BlockReason.NONE, "rules optional skip"
    if price <= 0:
        return False, BlockReason.INVALID_QUANTITY, "price<=0"
    if rules.tick_size <= 0:
        return False, BlockReason.MISSING_PRICE_RULES, "tick_size<=0"
    if not price_on_tick(price, rules.tick_size):
        return False, BlockReason.PRICE_NOT_ON_TICK, f"price {price} tick {rules.tick_size}"
    if rules.ara is not None and price > rules.ara + 1e-12:
        return False, BlockReason.PRICE_ABOVE_AR_LIMIT, f"price {price} > ARA {rules.ara}"
    if rules.arb is not None and price < rules.arb - 1e-12:
        return False, BlockReason.PRICE_BELOW_AR_LIMIT, f"price {price} < ARB {rules.arb}"
    return True, BlockReason.NONE, "ok"


def validate_order(
    order: OrderRequest,
    rules: Optional[PriceRules],
    *,
    require_rules: bool = True,
) -> Tuple[bool, BlockReason, str]:
    ok_q, r_q, d_q = validate_quantity(order.quantity, rules.lot_size if rules else 100)
    if not ok_q:
        return ok_q, r_q, d_q
    return validate_price(order.price, rules, require_rules=require_rules)
