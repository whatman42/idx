"""Crypto research plane — Turso optional, authority bounds, isolation from IDX."""
from __future__ import annotations

from src.python.crypto.colab_bridge import (
    colab_cannot_enable_live,
    colab_cannot_submit_orders,
    run_crypto_colab_research_stub,
)
from src.python.crypto.promotion_gate import CryptoPromotionGate
from src.python.crypto.research_memory import (
    CryptoMemoryStatus,
    connect_crypto_sqlite,
    crypto_memory_cannot_enable_live,
    crypto_memory_cannot_mutate_ledger,
)


def test_memory_authority_bounds():
    assert crypto_memory_cannot_mutate_ledger() is True
    assert crypto_memory_cannot_enable_live() is True
    mem = connect_crypto_sqlite(":memory:")
    assert mem.can_mutate_ledger is False
    assert mem.can_submit_orders is False
    assert mem.can_mutate_live_execution is False


def test_cycle_persist_sqlite_and_soft_fail():
    mem = connect_crypto_sqlite(":memory:")
    assert mem.status == CryptoMemoryStatus.AVAILABLE
    r = mem.record_cycle(
        {
            "status": "SUCCESS",
            "generated_at": "2026-09-29T00:00:00+00:00",
            "signal_coverage": "496/496",
            "signal_coverage_mode": "FULL_ELIGIBLE",
            "ohlcv_ok": 496,
            "ohlcv_attempted": 496,
            "signals_count": 10,
            "fills_paper": 2,
            "strategy_id": "crypto_rule_sma20",
            "universe": {"eligible_count": 496},
            "portfolio": {"equity": 9990.0},
        }
    )
    assert r["ok"] is True
    assert r["paper_blocked"] is False
    mem.record_strategy_version("crypto_rule_sma20", "crypto_sma_v0")
    assert mem.record_evidence(
        evidence_id="ev1",
        strategy_id="crypto_rule_sma20",
        payload={"n_trades": 5},
    )
    mem.close()


def test_unavailable_memory_does_not_block_paper():
    from src.python.crypto.research_memory import CryptoResearchMemory

    mem = CryptoResearchMemory(status=CryptoMemoryStatus.UNAVAILABLE)
    r = mem.record_cycle({"status": "SUCCESS"})
    assert r["ok"] is False
    assert r["paper_blocked"] is False


def test_promotion_gate_independent_and_no_live():
    gate = CryptoPromotionGate()
    d = gate.evaluate(
        strategy_id="rule_sma20",
        strategy_version="v0",
        evidence={"n_trades": 100, "expectancy": 1.0},
    )
    assert d.approved is False
    assert d.live_execution is False
    d2 = gate.evaluate(
        strategy_id="crypto_rule_sma20",
        strategy_version="crypto_sma_v0",
        evidence={"n_trades": 5, "expectancy": 0.1},
    )
    assert d2.lifecycle_status == "RESEARCH"
    assert d2.live_execution is False
    d3 = gate.evaluate(
        strategy_id="crypto_rule_sma20",
        strategy_version="crypto_sma_v0",
        evidence={"n_trades": 50, "expectancy": 0.1},
    )
    assert d3.approved is True
    assert d3.lifecycle_status == "CANDIDATE"
    assert d3.live_execution is False


def test_colab_stub_no_orders_no_live():
    assert colab_cannot_enable_live() is True
    assert colab_cannot_submit_orders() is True
    res = run_crypto_colab_research_stub(job_id="j1")
    assert res.live_execution is False
    assert res.orders_submitted == 0
    assert res.to_dict()["authority"] == "RESEARCH_ONLY"


def test_crypto_tables_not_idx_names():
    import inspect
    from src.python.crypto import research_memory as rm

    src = inspect.getsource(rm)
    assert "crypto_cycle_logs" in src
    assert "crypto_evidence" in src
    assert "CREATE TABLE IF NOT EXISTS experiments" not in src
