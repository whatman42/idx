"""Static + behavioral safety audit for crypto plane."""
from __future__ import annotations

import inspect
import pathlib

import pandas as pd

from src.python.crypto.config import CRYPTO_LIVE_EXECUTION, assert_crypto_paper_only
from src.python.crypto.promotion_gate import CryptoPromotionGate
from src.python.crypto.scorer import is_shadow_scorer
from src.python.crypto.execution import resolve_next_bar_open_fill

FORBIDDEN_SNIPS = (
    "create_order(",
    "cancel_order(",
    "place_order(",
    "/api/v3/order",
    "api/v3/order",
)


def test_no_order_endpoints_in_crypto_src():
    root = pathlib.Path("src/python/crypto")
    hits = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore").lower()
        for snip in FORBIDDEN_SNIPS:
            if snip in text:
                hits.append(f"{p}:{snip}")
    assert hits == [], hits


def test_live_hard_false():
    assert CRYPTO_LIVE_EXECUTION is False
    assert_crypto_paper_only()


def test_shadow_cannot_auto_paper():
    assert is_shadow_scorer("crypto_momentum_shadow")
    gate = CryptoPromotionGate()
    dec = gate.evaluate(
        strategy_id="crypto_momentum_shadow",
        strategy_version="crypto_mom_v0",
        evidence={
            "n_trades": 100,
            "expectancy": 1.0,
            "max_drawdown": 0.05,
            "hard_reject": [],
        },
        min_trades=10,
        promote_to_paper_allowed=True,
        persist=False,
    )
    assert dec.lifecycle_status != "PAPER_ALLOWED"
    assert "SHADOW" in " ".join(dec.reasons)


def test_next_bar_no_same_bar_fill():
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
            },
            {
                "symbol": "BTC/USDT",
                "timestamp": "2026-01-02T00:00:00+00:00",
                "open": 110.0,
                "high": 111.0,
                "low": 109.0,
                "close": 110.5,
                "volume": 1.0,
            },
        ]
    )
    r = resolve_next_bar_open_fill(
        bars, symbol="BTC/USDT", signal_timestamp="2026-01-01T00:00:00+00:00", slippage_bps=0
    )
    d = r.to_dict()
    assert r.status == "READY"
    assert d["same_bar_fill"] is False
    assert float(r.fill_open) == 110.0
    r2 = resolve_next_bar_open_fill(
        bars.iloc[:1], symbol="BTC/USDT", signal_timestamp="2026-01-01T00:00:00+00:00"
    )
    assert r2.status != "READY"


def test_evaluator_does_not_mutate_ledger():
    import src.python.crypto.evaluator as ev

    src = inspect.getsource(ev)
    assert "apply_buy" not in src
    assert "apply_sell" not in src
    assert ".save(" not in src
