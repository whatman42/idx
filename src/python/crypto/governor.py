"""Crypto governor — deterministic decision authority. PAPER ONLY."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from src.python.crypto.config import assert_crypto_paper_only


@dataclass
class GovernorDecision:
    state: str  # ALLOW | HOLD | BLOCK
    reason_code: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def govern(
    *,
    risk_allowed: bool,
    risk_reason: str = "",
    strategy_paper_allowed: bool = True,
    data_stale: bool = False,
    ledger_ok: bool = True,
    duplicate_signal: bool = False,
    execution_policy_ok: bool = True,
    feature_ok: bool = True,
    universe_ok: bool = True,
) -> GovernorDecision:
    assert_crypto_paper_only()
    if not execution_policy_ok:
        return GovernorDecision("BLOCK", "CRYPTO_EXECUTION_POLICY_INVALID")
    if not strategy_paper_allowed:
        return GovernorDecision("BLOCK", "CRYPTO_STRATEGY_NOT_PAPER_ALLOWED")
    if not ledger_ok:
        return GovernorDecision("BLOCK", "CRYPTO_LEDGER_INVALID")
    if duplicate_signal:
        return GovernorDecision("BLOCK", "CRYPTO_DUPLICATE_SIGNAL")
    if data_stale:
        return GovernorDecision("BLOCK", "CRYPTO_DATA_STALE")
    if not feature_ok:
        return GovernorDecision("BLOCK", "CRYPTO_FEATURE_INVALID")
    if not universe_ok:
        return GovernorDecision("BLOCK", "CRYPTO_UNIVERSE_UNKNOWN")
    if not risk_allowed:
        return GovernorDecision(
            "BLOCK",
            "CRYPTO_RISK_BLOCK",
            detail=str(risk_reason or ""),
        )
    return GovernorDecision("ALLOW", "CRYPTO_SIGNAL_APPROVED")
