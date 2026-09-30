"""Crypto plane configuration authority — isolated from IDX. PAPER ONLY."""
from __future__ import annotations

import os
from typing import Any

CRYPTO_BASE_CURRENCY = "USDT"
CRYPTO_LIVE_EXECUTION = False
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
CRYPTO_HOLD_BARS = int(os.getenv("CRYPTO_HOLD_BARS", "5"))
CRYPTO_STATE_PATH = os.getenv("CRYPTO_STATE_PATH", "state/crypto/paper_ledger.json")
CRYPTO_ENABLED = os.getenv("CRYPTO_ENABLED", "1").strip() not in ("0", "false", "FALSE", "no")
CRYPTO_EXECUTION_POLICY = os.getenv("CRYPTO_EXECUTION_POLICY", "NEXT_BAR_OPEN").strip().upper()
ALLOWED_EXECUTION_POLICIES = frozenset({"NEXT_BAR_OPEN"})
CRYPTO_FEATURE_VERSION = os.getenv("CRYPTO_FEATURE_VERSION", "crypto_feat_v1")
CRYPTO_STRATEGY_ID = os.getenv("CRYPTO_STRATEGY_ID", "crypto_rule_sma20")
CRYPTO_STRATEGY_VERSION = os.getenv("CRYPTO_STRATEGY_VERSION", "crypto_sma_v0")
CRYPTO_STALE_BARS_MAX = int(os.getenv("CRYPTO_STALE_BARS_MAX", "3"))
CRYPTO_MIN_HISTORY_BARS = int(os.getenv("CRYPTO_MIN_HISTORY_BARS", "25"))
CRYPTO_CONFIG_VERSION = "crypto_cfg_v1"


def assert_execution_policy() -> str:
    pol = CRYPTO_EXECUTION_POLICY
    if pol not in ALLOWED_EXECUTION_POLICIES:
        raise RuntimeError(
            f"CRYPTO_EXECUTION_POLICY_UNSUPPORTED:{pol}. "
            f"Allowed={sorted(ALLOWED_EXECUTION_POLICIES)}. "
            "SAME_BAR_CLOSE is intentionally not supported."
        )
    return pol


def assert_crypto_paper_only(*, live_flag: bool | None = None) -> None:
    env_live = os.getenv("CRYPTO_LIVE_EXECUTION", "").strip().lower() in (
        "1", "true", "yes", "on",
    )
    if live_flag is True or env_live or CRYPTO_LIVE_EXECUTION is True:
        raise RuntimeError(
            "CRYPTO_LIVE_EXECUTION_FORBIDDEN: paper plane only. "
            "Live/exchange order paths are not implemented and must not be enabled."
        )


def crypto_sim_assumptions() -> dict[str, Any]:
    return {
        "fee_model": "CRYPTO_SIMULATION",
        "buy_fee_bps": CRYPTO_FEE_BUY_BPS,
        "sell_fee_bps": CRYPTO_FEE_SELL_BPS,
        "slippage_bps": CRYPTO_SLIPPAGE_BPS,
        "tp_pct": CRYPTO_TP_PCT,
        "sl_pct": CRYPTO_SL_PCT,
        "hold_bars": CRYPTO_HOLD_BARS,
        "execution_policy": CRYPTO_EXECUTION_POLICY,
        "base_currency": CRYPTO_BASE_CURRENCY,
        "live_execution": False,
        "note": "Simulation assumptions — not exchange fee schedule fact.",
    }


def crypto_config_report() -> dict[str, Any]:
    assert_crypto_paper_only()
    assert_execution_policy()
    return {
        "config_version": CRYPTO_CONFIG_VERSION,
        "base_currency": CRYPTO_BASE_CURRENCY,
        "live_execution": False,
        "execution_policy": CRYPTO_EXECUTION_POLICY,
        "feature_version": CRYPTO_FEATURE_VERSION,
        "strategy_id": CRYPTO_STRATEGY_ID,
        "strategy_version": CRYPTO_STRATEGY_VERSION,
        "fee_model": crypto_sim_assumptions(),
        "universe_quote": CRYPTO_UNIVERSE_QUOTE,
        "data_provider": CRYPTO_DATA_PROVIDER,
        "max_weight": CRYPTO_MAX_WEIGHT,
        "max_positions": CRYPTO_MAX_POSITIONS,
        "stale_bars_max": CRYPTO_STALE_BARS_MAX,
        "min_history_bars": CRYPTO_MIN_HISTORY_BARS,
        "state_path": CRYPTO_STATE_PATH,
        "paper_only": True,
        "auto_promotion": False,
    }
