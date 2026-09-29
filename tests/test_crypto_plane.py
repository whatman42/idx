"""Crypto paper plane — isolation, USDT universe, safety, accounting."""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.python.crypto.config import (
    CRYPTO_BASE_CURRENCY,
    CRYPTO_LIVE_EXECUTION,
    assert_crypto_paper_only,
)
from src.python.crypto.models import ExclusionReason
from src.python.crypto.paper_ledger import CryptoPaperLedger
from src.python.crypto.provider import BinancePublicProvider
from src.python.crypto.risk import evaluate_crypto_entry
from src.python.crypto.strategy import STRATEGY_ID, crypto_sma20_signals


def test_live_execution_is_false():
    assert CRYPTO_LIVE_EXECUTION is False
    assert_crypto_paper_only()
    with pytest.raises(RuntimeError, match="CRYPTO_LIVE_EXECUTION_FORBIDDEN"):
        assert_crypto_paper_only(live_flag=True)


def test_usdt_base_currency():
    assert CRYPTO_BASE_CURRENCY == "USDT"
    led = CryptoPaperLedger.new_session(1000.0)
    assert led.base_currency == "USDT"


def _mock_exchange_info():
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "filters": [
                    {"filterType": "LOT_SIZE", "minQty": "0.00001", "stepSize": "0.00001"},
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    {"filterType": "NOTIONAL", "minNotional": "10"},
                ],
            },
            {
                "symbol": "ETHUSDT",
                "baseAsset": "ETH",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "filters": [
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    {"filterType": "NOTIONAL", "minNotional": "10"},
                ],
            },
            {
                "symbol": "SOLUSDT",
                "baseAsset": "SOL",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "filters": [
                    {"filterType": "LOT_SIZE", "minQty": "0.01", "stepSize": "0.01"},
                    {"filterType": "PRICE_FILTER", "tickSize": "0.001"},
                    {"filterType": "NOTIONAL", "minNotional": "5"},
                ],
            },
            {
                "symbol": "BTCBUSD",
                "baseAsset": "BTC",
                "quoteAsset": "BUSD",
                "status": "TRADING",
                "filters": [],
            },
            {
                "symbol": "ADABTC",
                "baseAsset": "ADA",
                "quoteAsset": "BTC",
                "status": "TRADING",
                "filters": [],
            },
            {
                "symbol": "XRPUSDT",
                "baseAsset": "XRP",
                "quoteAsset": "USDT",
                "status": "BREAK",
                "filters": [],
            },
            {
                "symbol": "BAD",
                "baseAsset": "",
                "quoteAsset": "USDT",
                "status": "TRADING",
                "filters": [],
            },
        ]
    }


def test_all_usdt_pairs_discovered_and_non_usdt_excluded():
    client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = _mock_exchange_info()
    resp.raise_for_status = MagicMock()
    client.get.return_value = resp
    report = BinancePublicProvider(client=client).discover_instruments()
    assert report.discovered_count == 7
    elig = {i.symbol for i in report.eligible}
    assert elig == {"BTC/USDT", "ETH/USDT", "SOL/USDT"}
    assert report.eligible_count == 3
    reasons = {i.block_reason for i in report.blocked}
    assert ExclusionReason.NON_USDT_QUOTE.value in reasons
    assert ExclusionReason.MARKET_INACTIVE.value in reasons
    assert ExclusionReason.INVALID_METADATA.value in reasons
    assert "SOL/USDT" in elig


def test_no_static_btc_eth_whitelist():
    import inspect
    from src.python.crypto import provider as pmod
    src = inspect.getsource(pmod.BinancePublicProvider.discover_instruments)
    assert "whitelist" not in src.lower()
    assert '["BTC"' not in src and "['BTC'" not in src


def test_universe_versioned_and_deterministic_shape():
    client = MagicMock()
    resp = MagicMock()
    resp.json.return_value = _mock_exchange_info()
    resp.raise_for_status = MagicMock()
    client.get.return_value = resp
    r1 = BinancePublicProvider(client=client).discover_instruments()
    r2 = BinancePublicProvider(client=client).discover_instruments()
    assert r1.universe_version
    assert r1.eligible_count == r2.eligible_count
    assert r1.provider == "binance_public"


def test_crypto_ledger_separate_and_invariant(tmp_path):
    path = str(tmp_path / "crypto_ledger.json")
    led = CryptoPaperLedger.new_session(10_000.0)
    f1 = led.apply_buy(symbol="BTC/USDT", price=50000.0, notional_usdt=1000.0, signal_id="s1")
    assert f1["status"] == "CRYPTO_PAPER_FILL"
    assert f1["broker"] == "NOT_SENT_NO_LIVE_EXECUTION"
    f2 = led.apply_buy(symbol="BTC/USDT", price=50000.0, notional_usdt=1000.0, signal_id="s1")
    assert f2["status"] == "ALREADY_APPLIED"
    marks = {"BTC/USDT": 50000.0}
    led.assert_invariant(marks)
    d = led.to_dict(marks)
    assert abs(d["cash"] + d["market_value"] - d["equity"]) < 1e-6
    led.save(path)
    led2 = CryptoPaperLedger.load(path)
    assert "BTC/USDT" in led2.positions
    assert "paper_portfolio" not in path


def test_crypto_does_not_use_bei_lot():
    led = CryptoPaperLedger.new_session(10_000.0)
    f = led.apply_buy(symbol="ETH/USDT", price=3000.0, notional_usdt=300.0, signal_id="e1", qty_precision=6)
    assert f["status"] == "CRYPTO_PAPER_FILL"
    assert abs(f["qty"] * f["price"] - f["notional"]) < 1e-3


def test_risk_fail_closed_unknown():
    d = evaluate_crypto_entry(equity_usdt=0, open_count=0, symbol="BTC/USDT", price=1.0)
    assert d.allow is False
    assert "FAIL_CLOSED" in d.reason
    d2 = evaluate_crypto_entry(equity_usdt=1000, open_count=0, symbol="BTC/USDT", price=None)
    assert d2.allow is False


def test_strategy_namespace_independent():
    assert STRATEGY_ID.startswith("crypto_")
    bars = pd.DataFrame(
        {
            "symbol": ["BTC/USDT"] * 30,
            "timestamp": [f"2026-01-{i+1:02d}T00:00:00+00:00" for i in range(30)],
            "open": [100.0 + i for i in range(30)],
            "high": [101.0 + i for i in range(30)],
            "low": [99.0 + i for i in range(30)],
            "close": [100.0 + i for i in range(30)],
            "volume": [1.0] * 30,
        }
    )
    sigs = crypto_sma20_signals(bars, lookback=20)
    assert all(s["market"] == "CRYPTO" for s in sigs)
    assert all(s["quote_currency"] == "USDT" for s in sigs)


def test_provider_rejects_non_usdt_ohlcv_symbol():
    prov = BinancePublicProvider(client=MagicMock())
    with pytest.raises(ValueError, match="NON_USDT"):
        prov.fetch_ohlcv("BTC/BTC")


def test_idx_universe_not_imported_in_crypto_signal():
    import src.python.crypto.signal_bot as sb
    import inspect
    src = inspect.getsource(sb)
    assert "paper_portfolio" not in src
    assert "idx_enrichment" not in src
    assert "ARA" not in src and "ARB" not in src
