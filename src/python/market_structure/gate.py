"""Market Structure / FCA execution gate — last-line check before OrderIntent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from src.python.market_structure.models import BlockReason, StructureGateResult
from src.python.market_structure.policy import evaluate_structure
from src.python.market_structure.provider import MarketStructureProvider


@dataclass
class ExecutionGate:
    provider: MarketStructureProvider
    max_age_seconds: float = 86_400.0
    on_blocked: Optional[Callable[[StructureGateResult], None]] = None
    broker_calls: list[str] = field(default_factory=list)

    def check_symbol(self, symbol: str, *, now=None) -> StructureGateResult:
        snap = self.provider.get(symbol)
        result = evaluate_structure(snap, max_age_seconds=self.max_age_seconds, now=now)
        if not result.allow and self.on_blocked:
            self.on_blocked(result)
        return result

    def allow_order_intent(self, symbol: str, *, now=None) -> StructureGateResult:
        return self.check_symbol(symbol, now=now)

    def recheck_before_execution(
        self,
        symbol: str,
        *,
        prior: Optional[StructureGateResult] = None,
        now=None,
    ) -> StructureGateResult:
        current = self.check_symbol(symbol, now=now)
        if prior is not None and prior.allow and not current.allow:
            return StructureGateResult(
                allow=False,
                reason=BlockReason.STRUCTURE_CHANGED,
                symbol=current.symbol,
                market_mode=current.market_mode,
                detected_at=current.detected_at,
                source=current.source,
                detail=f"was {prior.market_mode} → now {current.market_mode}",
                policy=current.policy,
            )
        return current

    def assert_never_broker(self) -> None:
        if self.broker_calls:
            raise AssertionError(f"broker endpoint called: {self.broker_calls}")


def gemini_cannot_override(gate_result: StructureGateResult, gemini_says_ok: bool) -> StructureGateResult:
    """LLM opinion never flips a BLOCK to PASS."""
    _ = gemini_says_ok
    return gate_result
