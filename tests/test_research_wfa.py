"""WFA executor, regime idempotency, experiment immutability, promotion safety."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.python.learning.contracts import SignalEpisode
from src.python.research.budget import ResearchBudget
from src.python.research.colab_jobs import ResearchJobKind, make_job
from src.python.research.experiment_result import ExperimentResultStore
from src.python.research.queue import ResearchQueue
from src.python.research.regime_matrix import RegimeMatrix
from src.python.research.wfa_executor import (
    WFAExecutor,
    experiment_result_to_evidence,
    validate_pit_features,
)


def _bars(n: int = 120, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.2, n)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="B"),
        "symbol": "BBCA",
        "open": open_,
        "high": np.maximum(open_, close) + 0.5,
        "low": np.minimum(open_, close) - 0.5,
        "close": close,
        "volume": rng.integers(1e5, 1e6, n),
    })


def _ep(i: int, **kw) -> SignalEpisode:
    base = dict(
        episode_id=f"E{i}",
        trading_date="2026-09-19",
        symbol="BBCA",
        strategy_id="rule_sma20",
        regime="SIDEWAYS",
        r_multiple=-0.5,
        pnl=-10.0,
        outcome="LOSS",
        lifecycle="COMPLETED",
        fill_id=f"F{i}",
        idempotency_key=f"K{i}",
    )
    base.update(kw)
    return SignalEpisode(**base)


def test_regime_matrix_idempotent_same_episodes():
    m = RegimeMatrix()
    eps = [_ep(i) for i in range(6)]
    m.observe_many(eps)
    snap = m.to_dict()
    m.observe_many(eps)
    assert m.to_dict()["n_seen_episodes"] == snap["n_seen_episodes"]
    assert m.to_dict()["cells"] == snap["cells"]
    m2 = RegimeMatrix()
    m2.rebuild(eps)
    assert m2.to_dict()["cells"] == snap["cells"]


def test_wfa_point_in_time_guard():
    bars = _bars()
    bars["future_return"] = bars["close"].shift(-1)
    assert validate_pit_features(bars)
    job = make_job(job_id="J-PIT", kind=ResearchJobKind.WALK_FORWARD, experiment_id="EXP-PIT", strategy_id="sma")
    res = WFAExecutor().execute(job, bars)
    assert res.status == "INVALID"
    assert "lookahead" in str(res.integrity_checks.get("fail_reason", "")) or res.leakage_checks.get("future_cols")


def test_wfa_deterministic_and_idempotent(tmp_path):
    bars = _bars(150, seed=7)
    job = make_job(
        job_id="J-WFA",
        kind=ResearchJobKind.WALK_FORWARD,
        experiment_id="EXP-WFA",
        strategy_id="rule_sma20",
        parameters={"sma_window": 20, "n_windows": 3},
        dataset_hash="synth",
        random_seed=7,
    )
    store = ExperimentResultStore(tmp_path)
    exe = WFAExecutor(store=store)
    r1 = exe.execute(job, bars)
    r2 = exe.execute(job, bars)
    assert r1.result_hash == r2.result_hash
    assert r1.status in ("COMPLETED", "ROBUST", "FRAGILE", "INSUFFICIENT_EVIDENCE")
    assert r1.integrity_checks.get("champion_write") is False
    assert r1.cost_model_detail.get("fee_bps") == 15.0
    assert r1.cost_model_detail.get("exit_fee_bps") == 25.0
    assert r1.cost_model_detail.get("slippage_bps") == 5.0


def test_executor_cannot_write_champion():
    bars = _bars()
    job = make_job(job_id="J-CH", kind=ResearchJobKind.WALK_FORWARD, experiment_id="EXP-CH", strategy_id="sma")
    with pytest.raises(PermissionError):
        WFAExecutor().execute(job, bars, allow_champion_write=True)


def test_auto_promote_rejected_on_job():
    with pytest.raises(ValueError, match="auto_promote"):
        make_job(
            job_id="J-AP",
            kind=ResearchJobKind.WALK_FORWARD,
            experiment_id="EXP-AP",
            parameters={"auto_promote": True},
        )


def test_evidence_never_auto_approved():
    bars = _bars(150, seed=1)
    job = make_job(job_id="J-EV", kind=ResearchJobKind.WALK_FORWARD, experiment_id="EXP-EV", strategy_id="sma")
    res = WFAExecutor().execute(job, bars)
    ev = experiment_result_to_evidence(res)
    assert ev["auto_promote"] is False
    assert ev["approved"] is False
    assert ev["walk_forward"] is True


def test_budget_and_queue_idempotent():
    b = ResearchBudget(max_jobs_per_cycle=2, max_total_research_budget_sec=100)
    q = ResearchQueue(budget=b)
    j1 = make_job(job_id="Q1", kind=ResearchJobKind.WALK_FORWARD, experiment_id="E1", strategy_id="s", budget_sec=40)
    j2 = make_job(job_id="Q2", kind=ResearchJobKind.WALK_FORWARD, experiment_id="E2", strategy_id="s", budget_sec=40)
    j3 = make_job(job_id="Q3", kind=ResearchJobKind.WALK_FORWARD, experiment_id="E3", strategy_id="s", budget_sec=40)
    assert q.enqueue(j1).status == "QUEUED"
    assert q.enqueue(j1).status == "QUEUED"
    assert q.enqueue(j2).status == "QUEUED"
    q.next_job()
    q.next_job()
    assert q.enqueue(j3).status == "BLOCKED"


def test_job_provenance_fingerprint_stable():
    j = make_job(job_id="J-FP", kind=ResearchJobKind.WALK_FORWARD, experiment_id="E-FP", strategy_id="sma", commit_sha="abc")
    assert len(j.configuration_fingerprint()) == 24
    assert j.configuration_fingerprint() == j.configuration_fingerprint()
