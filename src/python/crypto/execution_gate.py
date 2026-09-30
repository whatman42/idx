"""Paper execution gate — last boundary before fill intent. PAPER ONLY."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from src.python.crypto.config import (
    CRYPTO_EXECUTION_POLICY,
    assert_crypto_paper_only,
    assert_execution_policy,
)
from src.python.crypto.execution import resolve_next_bar_open_fill


@dataclass
class GateResult:
    allowed: bool
    reason_code: str
    fill_price: Optional[float] = None
    fill_timestamp: Optional[str] = None
    fill_open: Optional[float] = None
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def paper_execution_gate(
    *,
    bars,
    symbol: str,
    signal_timestamp: str,
    strategy_paper_allowed: bool,
    governor_state: str,
    ledger_healthy: bool,
    already_applied: bool,
    quote_asset: str = "USDT",
    slippage_bps: float = 5.0,
) -> GateResult:
    assert_crypto_paper_only()
    try:
        assert_execution_policy()
    except RuntimeError as e:
        return GateResult(False, "CRYPTO_EXECUTION_POLICY_INVALID", detail=str(e))

    if CRYPTO_EXECUTION_POLICY != "NEXT_BAR_OPEN":
        return GateResult(False, "CRYPTO_EXECUTION_POLICY_INVALID")
    if not strategy_paper_allowed:
        return GateResult(False, "CRYPTO_STRATEGY_NOT_PAPER_ALLOWED")
    if governor_state != "ALLOW":
        return GateResult(False, "CRYPTO_GOVERNOR_BLOCK", detail=governor_state)
    if not ledger_healthy:
        return GateResult(False, "CRYPTO_LEDGER_INVALID")
    if already_applied:
        return GateResult(False, "CRYPTO_DUPLICATE_SIGNAL")
    if not symbol or "/" not in symbol:
        return GateResult(False, "CRYPTO_INVALID_SYMBOL")
    if not str(symbol).endswith(f"/{quote_asset}"):
        return GateResult(False, "CRYPTO_INVALID_QUOTE")

    resolved = resolve_next_bar_open_fill(
        bars,
        symbol=symbol,
        signal_timestamp=str(signal_timestamp),
        slippage_bps=slippage_bps,
    )
    if resolved.status != "READY":
        return GateResult(False, "CRYPTO_NO_FILL", detail=str(resolved.status))
    px = float(resolved.fill_price or 0)
    if px <= 0:
        return GateResult(False, "CRYPTO_INVALID_PRICE")
    return GateResult(
        True,
        "CRYPTO_GATE_PASS",
        fill_price=px,
        fill_timestamp=resolved.fill_timestamp,
        fill_open=resolved.fill_open,
    )
