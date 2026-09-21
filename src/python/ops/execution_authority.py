"""Single execution authority — Market Structure Gate before any fill.

OrderRequest → Gate → ValidatedOrder → Executor (paper/broker adapter)
No alternate path may call paper fill / broker without clearance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.python.market_structure import (
    ExecutionGate,
    MarketStructureProvider,
    OrderRequest,
    StructureGateResult,
)


@dataclass(frozen=True)
class ValidatedOrder:
    symbol: str
    side: int
    price: float
    quantity: int
    signal_id: str
    gate_result: StructureGateResult
    clearance_id: str


def default_continuous_provider(symbols: list[str] | None = None) -> MarketStructureProvider:
    """Explicit CONTINUOUS map only for listed symbols; others → UNKNOWN → BLOCK."""
    syms = symbols or []
    return MarketStructureProvider.from_status_map({s: "CONTINUOUS" for s in syms})


def clear_for_execution(
    gate: ExecutionGate,
    order: OrderRequest,
    *,
    prior: Optional[StructureGateResult] = None,
    now=None,
) -> tuple[Optional[ValidatedOrder], StructureGateResult]:
    """Mandatory recheck immediately before execution."""
    result = gate.recheck_before_execution(order.symbol, prior=prior, order=order, now=now)
    if not result.allow:
        return None, result
    import hashlib

    cid = hashlib.sha256(
        f"{order.symbol}|{order.side}|{order.price}|{order.quantity}|{order.signal_id}|{result.detected_at}".encode()
    ).hexdigest()[:16]
    vo = ValidatedOrder(
        symbol=order.symbol.upper(),
        side=order.side,
        price=float(order.price),
        quantity=int(order.quantity),
        signal_id=order.signal_id,
        gate_result=result,
        clearance_id=cid,
    )
    return vo, result


def block_status_code(result: StructureGateResult) -> str:
    return f"SKIPPED_MS_{result.reason.value}"
