"""P3: SMA20 reference + momentum shadow — no auto paper."""
from __future__ import annotations

import pandas as pd

from src.python.crypto.feature_snapshot import CryptoFeatureSnapshot
from src.python.crypto.promotion_gate import CryptoPromotionGate
from src.python.crypto.scorer import (
    CryptoMomentumShadowScorer,
    get_crypto_scorer,
    is_shadow_scorer,
)
from src.python.crypto.shadow_eval import REFERENCE_ID, SHADOW_ID, run_shadow_comparison


def _trend_bars(n: int = 50) -> pd.DataFrame:
    rows = []
    px = 100.0
    for i in range(n):
        px *= 1.015
        rows.append(
            {
                "timestamp": f"2026-08-01T{i:02d}:00:00+00:00",
                "symbol": "BTC/USDT",
                "open": px * 0.999,
                "high": px * 1.01,
                "low": px * 0.99,
                "close": px,
                "volume": 100.0 + i,
            }
        )
    return pd.DataFrame(rows)


def test_shadow_scorer_uses_snapshot():
    scorer = CryptoMomentumShadowScorer()
    assert scorer.plane == "SHADOW"
    r = scorer.score_row(
        CryptoFeatureSnapshot(
            timestamp="t",
            symbol="BTC/USDT",
            features={"ret_5": 0.02, "sma_dist_20": 0.01, "close": 100.0, "vol_z_20": 0.5},
        )
    )
    assert r["side"] == 1


def test_is_shadow_flag():
    assert is_shadow_scorer(SHADOW_ID)
    assert not is_shadow_scorer(REFERENCE_ID)


def test_shadow_cannot_auto_paper_allowed():
    gate = CryptoPromotionGate()
    dec = gate.evaluate(
        strategy_id=SHADOW_ID,
        strategy_version="crypto_mom_v0",
        evidence={"n_trades": 50, "expectancy": 1.0, "max_drawdown": 0.1, "hard_reject": []},
        min_trades=30,
        promote_to_paper_allowed=True,
        persist=False,
    )
    assert dec.lifecycle_status == "CANDIDATE"
    assert dec.lifecycle_status != "PAPER_ALLOWED"
    assert "SHADOW_RESEARCH_ONLY" in dec.reasons or "SHADOW_CANNOT_AUTO_PAPER" in dec.reasons


def test_run_shadow_comparison_invariants():
    out = run_shadow_comparison(_trend_bars(50), persist_gate=False)
    assert out["live_execution"] is False
    assert out["invariants"]["shadow_auto_paper_allowed"] is False
    assert out["shadow"]["paper_eligible"] is False
    assert out["shadow"]["gate"]["lifecycle_status"] != "PAPER_ALLOWED"


def test_get_scorer_registry():
    assert get_crypto_scorer(REFERENCE_ID).strategy_id == REFERENCE_ID
    assert get_crypto_scorer(SHADOW_ID).strategy_id == SHADOW_ID
