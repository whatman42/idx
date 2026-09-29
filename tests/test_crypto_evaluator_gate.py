"""Crypto P1 — evaluator, strategy status gate, research pipeline."""
from __future__ import annotations

import pandas as pd

from src.python.crypto.colab_bridge import run_crypto_research_pipeline
from src.python.crypto.evaluator import backtest_crypto, build_evidence_package, walk_forward_crypto
from src.python.crypto.promotion_gate import CryptoPromotionGate
from src.python.crypto.strategy_status import (
    StrategyStatusRecord,
    get_status,
    paper_ops_allowed,
    set_status,
)


def _bars(n: int = 80, sym: str = "BTC/USDT") -> pd.DataFrame:
    rows = []
    px = 100.0
    for i in range(n):
        px = px * (1.01 if i % 7 != 0 else 0.99)
        rows.append(
            {
                "timestamp": f"2026-03-01T{i:02d}:00:00+00:00" if i < 24 else f"2026-03-02T{i-24:02d}:00:00+00:00",
                "symbol": sym,
                "open": px,
                "high": px * 1.01,
                "low": px * 0.99,
                "close": px,
                "volume": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_backtest_usdt_no_bei_lot():
    res = backtest_crypto(_bars())
    assert res["base_currency"] == "USDT"
    assert res["live_execution"] is False
    assert res["plane"] == "CRYPTO_RESEARCH"


def test_walk_forward_and_evidence():
    bars = _bars(90)
    bt = backtest_crypto(bars)
    wf = walk_forward_crypto(bars)
    ev = build_evidence_package(
        strategy_id="crypto_rule_sma20",
        strategy_version="crypto_sma_v0",
        backtest=bt,
        walk_forward=wf,
    )
    assert ev["domain"] == "CRYPTO"
    assert ev["live_execution"] is False


def test_research_not_silently_paper_allowed(tmp_path):
    path = str(tmp_path / "st.json")
    rec = get_status("crypto_rule_sma20", "v0", path=path)
    assert rec.status == "RESEARCH"
    ok, reason = paper_ops_allowed(
        "crypto_rule_sma20", "v0", path=path, allow_research_experiment=False
    )
    assert ok is False and reason == "RESEARCH_REQUIRES_FLAG"
    ok2, reason2 = paper_ops_allowed(
        "crypto_rule_sma20", "v0", path=path, allow_research_experiment=True
    )
    assert ok2 is True and reason2 == "RESEARCH_EXPERIMENTATION"


def test_gate_persists_candidate_not_promoted_without_flag(tmp_path):
    path = str(tmp_path / "st.json")
    d = CryptoPromotionGate().evaluate(
        strategy_id="crypto_rule_sma20",
        strategy_version="v1",
        evidence={"n_trades": 50, "expectancy": 1.0, "max_drawdown": 0.1},
        promote_to_paper_allowed=False,
        persist=True,
        status_path=path,
    )
    assert d.lifecycle_status == "CANDIDATE"
    assert d.live_execution is False
    assert get_status("crypto_rule_sma20", "v1", path=path).status == "CANDIDATE"


def test_pipeline_end_to_end(tmp_path):
    res = run_crypto_research_pipeline(
        job_id="t1", bars=_bars(100), status_path=str(tmp_path / "st.json"), run_gate=True
    )
    assert res.live_execution is False and res.orders_submitted == 0
    assert res.evidence["domain"] == "CRYPTO"


def test_rejected_blocks_paper(tmp_path):
    path = str(tmp_path / "st.json")
    set_status(StrategyStatusRecord("crypto_x", "v0", "REJECTED", ["test"]), path=path)
    ok, reason = paper_ops_allowed("crypto_x", "v0", path=path)
    assert ok is False and reason == "REJECTED"
