"""Operational maturity parity tests — crypto plane only. PAPER ONLY."""
from __future__ import annotations

import pandas as pd
import pytest

from src.python.crypto.config import (
    crypto_config_report,
    assert_crypto_paper_only,
    CRYPTO_EXECUTION_POLICY,
)
from src.python.crypto.governor import govern
from src.python.crypto.execution_gate import paper_execution_gate
from src.python.crypto.signal_contract import build_signal
from src.python.crypto.risk import evaluate_crypto_entry
from src.python.crypto.cycle import new_cycle_id
from src.python.crypto.data_quality import validate_ohlcv_frame
from src.python.crypto.paper_ledger import CryptoPaperLedger
from src.python.crypto.strategy_status import paper_ops_allowed
from src.python.crypto.strategy import STRATEGY_ID, STRATEGY_VERSION


def test_config_contract_report():
    r = crypto_config_report()
    assert r["live_execution"] is False
    assert r["paper_only"] is True
    assert r["auto_promotion"] is False
    assert r["execution_policy"] == "NEXT_BAR_OPEN"
    assert r["base_currency"] == "USDT"


def test_live_env_forbidden(monkeypatch):
    monkeypatch.setenv("CRYPTO_LIVE_EXECUTION", "true")
    with pytest.raises(RuntimeError, match="LIVE"):
        assert_crypto_paper_only()


def test_governor_allow_and_blocks():
    assert govern(risk_allowed=True).state == "ALLOW"
    assert govern(risk_allowed=False, risk_reason="X").reason_code == "CRYPTO_RISK_BLOCK"
    assert govern(risk_allowed=True, strategy_paper_allowed=False).reason_code == (
        "CRYPTO_STRATEGY_NOT_PAPER_ALLOWED"
    )
    assert govern(risk_allowed=True, data_stale=True).reason_code == "CRYPTO_DATA_STALE"
    assert govern(risk_allowed=True, ledger_ok=False).reason_code == "CRYPTO_LEDGER_INVALID"
    assert govern(risk_allowed=True, duplicate_signal=True).reason_code == (
        "CRYPTO_DUPLICATE_SIGNAL"
    )


def test_signal_contract_not_a_fill():
    s = build_signal(
        cycle_id="C1",
        symbol="BTC/USDT",
        signal_timestamp="2026-01-01T00:00:00+00:00",
        reference_price=100.0,
    )
    d = s.to_dict()
    assert d["is_fill"] is False
    assert d["live_execution"] is False
    assert d["executable_at"] == "T+1_OPEN"
    assert d["execution_policy"] == "NEXT_BAR_OPEN"


def test_execution_gate_no_t1():
    bars = pd.DataFrame(
        [
            {
                "symbol": "BTC/USDT",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1.0,
            }
        ]
    )
    g = paper_execution_gate(
        bars=bars,
        symbol="BTC/USDT",
        signal_timestamp="2026-01-01T00:00:00+00:00",
        strategy_paper_allowed=True,
        governor_state="ALLOW",
        ledger_healthy=True,
        already_applied=False,
    )
    assert g.allowed is False


def test_execution_gate_next_open():
    bars = pd.DataFrame(
        [
            {
                "symbol": "ETH/USDT",
                "timestamp": "2026-01-01T00:00:00+00:00",
                "open": 10.0,
                "high": 11.0,
                "low": 9.0,
                "close": 10.5,
                "volume": 1.0,
            },
            {
                "symbol": "ETH/USDT",
                "timestamp": "2026-01-02T00:00:00+00:00",
                "open": 12.0,
                "high": 13.0,
                "low": 11.0,
                "close": 12.5,
                "volume": 1.0,
            },
        ]
    )
    g = paper_execution_gate(
        bars=bars,
        symbol="ETH/USDT",
        signal_timestamp="2026-01-01T00:00:00+00:00",
        strategy_paper_allowed=True,
        governor_state="ALLOW",
        ledger_healthy=True,
        already_applied=False,
        slippage_bps=0.0,
    )
    assert g.allowed is True
    assert g.fill_open == 12.0


def test_risk_fail_closed():
    assert not evaluate_crypto_entry(
        equity_usdt=1000, open_count=0, symbol="BTCUSDT", price=1
    ).allowed
    assert not evaluate_crypto_entry(
        equity_usdt=0, open_count=0, symbol="BTC/USDT", price=1
    ).allowed
    assert not evaluate_crypto_entry(
        equity_usdt=1000, open_count=0, symbol="BTC/USDT", price=1, data_stale=True
    ).allowed


def test_ledger_invariant_and_idempotency():
    led = CryptoPaperLedger.new_session()
    marks = {"BTC/USDT": 100.0}
    led.assert_invariant(marks)
    r1 = led.apply_buy(
        symbol="BTC/USDT", price=100.0, notional_usdt=500.0, signal_id="s1"
    )
    assert r1.get("status") == "CRYPTO_PAPER_FILL"
    r2 = led.apply_buy(
        symbol="BTC/USDT", price=100.0, notional_usdt=500.0, signal_id="s1"
    )
    assert r2.get("status") == "ALREADY_APPLIED"


def test_cycle_id_unique():
    a, b = new_cycle_id(), new_cycle_id()
    assert a != b
    assert a.startswith("CRYPTO-")


def test_data_quality_impossible_ohlc():
    df = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "open": 10.0,
                "high": 9.0,
                "low": 11.0,
                "close": 10.0,
            }
        ]
    )
    v = validate_ohlcv_frame(df, symbol="X/USDT")
    assert v["ok"] is False


def test_sma20_paper_allowed_shadow_not_auto():
    from src.python.crypto.scorer import is_shadow_scorer

    assert is_shadow_scorer("crypto_momentum_shadow") is True
    assert is_shadow_scorer(STRATEGY_ID) is False


def test_execution_policy_ssot():
    assert CRYPTO_EXECUTION_POLICY == "NEXT_BAR_OPEN"
