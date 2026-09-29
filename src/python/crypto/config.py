"""Crypto plane configuration — isolated from IDX env."""
from __future__ import annotations

import os

CRYPTO_BASE_CURRENCY = "USDT"
CRYPTO_LIVE_EXECUTION = False  # HARD — never True in this package
CRYPTO_UNIVERSE_QUOTE = "USDT"
CRYPTO_DATA_PROVIDER = os.getenv("CRYPTO_DATA_PROVIDER", "binance_public")
CRYPTO_FEE_BUY_BPS = float(os.getenv("CRYPTO_FEE_BUY_BPS", "10"))
CRYPTO_FEE_SELL_BPS = float(os.getenv("CRYPTO_FEE_SELL_BPS", "10"))
CRYPTO_SLIPPAGE_BPS = float(os.getenv("CRYPTO_SLIPPAGE_BPS", "5"))
CRYPTO_INITIAL_CAPITAL_USDT = float(os.getenv("CRYPTO_INITIAL_CAPITAL_USDT", "10000"))
CRYPTO_MAX_WEIGHT = float(os.getenv("CRYPTO_MAX_WEIGHT", "0.15"))
CRYPTO_MAX_POSITIONS = int(os.getenv("CRYPTO_MAX_POSITIONS", "10"))
CRYPTO_TP_PCT = float(os.getenv("CRYPTO_TP_PCT", "0.06"))
CRYPTO_SL_PCT = float(os.getenv("CRYPTO_SL_PCT", "0.03"))
CRYPTO_STATE_PATH = os.getenv("CRYPTO_STATE_PATH", "state/crypto/paper_ledger.json")
CRYPTO_ENABLED = os.getenv("CRYPTO_ENABLED", "1").strip() not in ("0", "false", "FALSE", "no")


def assert_crypto_paper_only(*, live_flag: bool | None = None) -> None:
    """Fail-closed if any path attempts live execution."""
    env_live = os.getenv("CRYPTO_LIVE_EXECUTION", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if CRYPTO_LIVE_EXECUTION or env_live or live_flag is True:
        raise RuntimeError(
            "CRYPTO_LIVE_EXECUTION_FORBIDDEN: crypto plane is PAPER ONLY. "
            "No exchange order submission path exists."
        )


def crypto_sim_assumptions() -> dict:
    return {
        "fee_model": "CRYPTO_SIMULATION",
        "buy_fee_bps": CRYPTO_FEE_BUY_BPS,
        "sell_fee_bps": CRYPTO_FEE_SELL_BPS,
        "slippage_bps": CRYPTO_SLIPPAGE_BPS,
        "tp_pct": CRYPTO_TP_PCT,
        "sl_pct": CRYPTO_SL_PCT,
        "base_currency": CRYPTO_BASE_CURRENCY,
        "live_execution": False,
        "note": "Simulation assumptions — not exchange fee schedule fact.",
    }
