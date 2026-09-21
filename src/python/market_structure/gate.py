"""Final execution safety gate: structure + session + price/lot rules."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional

from src.python.market_structure.models import (
    BlockReason,
    OrderRequest,
    PriceRules,
    StructureGateResult,
)
from src.python.market_structure.policy import evaluate_structure
from src.python.market_structure.price_rules import validate_order
from src.python.market_structure.provider import MarketStructureProvider


@dataclass
class ExecutionGate:
    provider: MarketStructureProvider
    price_rules: Mapping[str, PriceRules] = field(default_factory=dict)
    max_age_seconds: float = 86_400.0
    require_open_session: bool = True
    require_price_rules: bool = True
    on_blocked: Optional[Callable[[StructureGateResult], None]] = None
    broker_calls: list[str] = field(default_factory=list)

    def check_symbol(self, symbol: str, *, now=None) -> StructureGateResult:
        snap = self.provider.get(symbol)
        result = evaluate_structure(
            snap,
            max_age_seconds=self.max_age_seconds,
            now=now,
            require_open_session=self.require_open_session,
        )
        if not result.allow and self.on_blocked:
            self.on_blocked(result)
        return result

    def allow_order_intent(self, symbol: str, *, now=None) -> StructureGateResult:
        return self.check_symbol(symbol, now=now)

    def validate_order_request(self, order: OrderRequest, *, now=None) -> StructureGateResult:
        base = self.check_symbol(order.symbol, now=now)
        if not base.allow:
            return base
        rules = self.price_rules.get(order.symbol.upper()) or self.price_rules.get(order.symbol)
        ok, reason, detail = validate_order(order, rules, require_rules=self.require_price_rules)
        if not ok:
            return StructureGateResult(
                allow=False,
                reason=reason,
                symbol=base.symbol,
                market_mode=base.market_mode,
                detected_at=base.detected_at,
                source=base.source,
                detail=detail,
                policy=base.policy,
                session=base.session,
                eligibility=base.eligibility,
            )
        return StructureGateResult(
            allow=True,
            reason=BlockReason.NONE,
            symbol=base.symbol,
            market_mode=base.market_mode,
            detected_at=base.detected_at,
            source=base.source,
            detail="structure+price ok",
            policy=base.policy,
            session=base.session,
            eligibility=base.eligibility,
            normalized_price=order.price,
            normalized_qty=order.quantity,
        )

    def recheck_before_execution(
        self,
        symbol: str,
        *,
        prior: Optional[StructureGateResult] = None,
        order: Optional[OrderRequest] = None,
        now=None,
    ) -> StructureGateResult:
        current = self.validate_order_request(order, now=now) if order is not None else self.check_symbol(symbol, now=now)
        if prior is not None and prior.allow and not current.allow:
            return StructureGateResult(
                allow=False,
                reason=BlockReason.STRUCTURE_CHANGED,
                symbol=current.symbol,
                market_mode=current.market_mode,
                detected_at=current.detected_at,
                source=current.source,
                detail=f"was {prior.market_mode}/{prior.session} → now {current.market_mode}/{current.session}",
                policy=current.policy,
                session=current.session,
                eligibility=current.eligibility,
            )
        return current

    def assert_never_broker(self) -> None:
        if self.broker_calls:
            raise AssertionError(f"broker endpoint called: {self.broker_calls}")


def gemini_cannot_override(gate_result: StructureGateResult, gemini_says_ok: bool) -> StructureGateResult:
    _ = gemini_says_ok
    return gate_result
