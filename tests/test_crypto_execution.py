"""NEXT_BAR_OPEN execution policy — paper aligned with evaluator."""
from __future__ import annotations

import pandas as pd
import pytest

from src.python.crypto.config import assert_execution_policy
from src.python.crypto.execution import intents_from_signals, resolve_next_bar_open_fill
from src.python.crypto.scorer import latest_executable_long_signals


def _bars_pair() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp": "2026-05-01T00:00:00+00:00",
                "symbol": "BTC/USDT",
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.5,
                "volume": 1.0,
            },
            {
                "timestamp": "2026-05-02T00:00:00+00:00",
                "symbol": "BTC/USDT",
                "open": 110.0,
                "high": 112.0,
                "low": 109.0,
                "close": 111.0,
                "volume": 1.0,
            },
        ]
    )


def test_policy_is_next_bar_open():
    assert assert_execution_policy() == "NEXT_BAR_OPEN"


def test_signal_t_fills_open_t1_with_slippage():
    r = resolve_next_bar_open_fill(
        _bars_pair(),
        symbol="BTC/USDT",
        signal_timestamp="2026-05-01T00:00:00+00:00",
        slippage_bps=10.0,
    )
    assert r.status == "READY"
    assert r.fill_open == 110.0
    assert r.fill_price == pytest.approx(110.0 * 1.001)
    assert r.fill_timestamp.startswith("2026-05-02")
    assert r.fill_price != 100.5


def test_no_same_bar_fill_on_last_bar():
    r = resolve_next_bar_open_fill(
        _bars_pair(),
        symbol="BTC/USDT",
        signal_timestamp="2026-05-02T00:00:00+00:00",
        slippage_bps=5.0,
    )
    assert r.status == "NO_NEXT_BAR"
    assert r.reason == "NO_BAR_AFTER_SIGNAL"


def test_missing_symbol_no_fill():
    r = resolve_next_bar_open_fill(
        _bars_pair(),
        symbol="ETH/USDT",
        signal_timestamp="2026-05-01T00:00:00+00:00",
    )
    assert r.status == "NO_NEXT_BAR"


def test_intents_reference_only():
    intents = intents_from_signals(
        [{"symbol": "BTC/USDT", "timestamp": "2026-05-01T00:00:00+00:00", "price": 100.5}]
    )
    assert intents[0].signal_close == 100.5


def test_executable_signals_require_t_plus_1():
    rows = []
    px = 100.0
    for i in range(30):
        px *= 1.02
        rows.append(
            {
                "timestamp": f"2026-06-01T{i:02d}:00:00+00:00",
                "symbol": "AAA/USDT",
                "open": px,
                "high": px * 1.01,
                "low": px * 0.99,
                "close": px,
                "volume": 10.0,
            }
        )
    bars = pd.DataFrame(rows)
    for s in latest_executable_long_signals(bars):
        r = resolve_next_bar_open_fill(
            bars, symbol=s["symbol"], signal_timestamp=s["timestamp"], slippage_bps=5.0
        )
        assert r.status == "READY"
        assert r.fill_timestamp != s["timestamp"]
