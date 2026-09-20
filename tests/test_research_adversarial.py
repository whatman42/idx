"""Adversarial / institutional certification tests for Research Plane."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.python.research.colab_jobs import ResearchJobKind, make_job
from src.python.research.evidence_bridge import (
    evaluate_research_candidacy,
    experiment_result_to_evidence_package,
)
from src.python.research.experiment_result import ExperimentResult, ExperimentResultStore
from src.python.research.feedback import feedback_experiment_to_knowledge
from src.python.research.invariants import (
    check_anti_overfit_gate,
    check_result_provenance,
    check_tamper,
)
from src.python.research.reproducibility import (
    fingerprint_changes_when_input_changes,
    verify_reproducibility,
)
from src.python.research.wfa_executor import WFAExecutor


def _bars(n=150, seed=7):
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


def _job(**kw):
    base = dict(
        job_id="J-ADV",
        kind=ResearchJobKind.WALK_FORWARD,
        experiment_id="EXP-ADV",
        strategy_id="rule_sma20",
        parameters={"sma_window": 20, "n_windows": 3},
        dataset_hash="ds-v1",
        feature_hash="ft-v1",
        commit_sha="cafebabe",
        random_seed=7,
    )
    base.update(kw)
    return make_job(**base)


def test_research_cannot_write_champion():
    with pytest.raises(PermissionError):
        WFAExecutor().execute(_job(), _bars(), allow_champion_write=True)


def test_auto_promote_job_rejected():
    with pytest.raises(ValueError, match="auto_promote"):
        make_job(job_id="x", kind=ResearchJobKind.WALK_FORWARD, experiment_id="e",
                 strategy_id="s", parameters={"auto_promote": True})


def test_candidacy_approved_always_false():
    res = WFAExecutor().execute(_job(experiment_id="EXP-APPR"), _bars())
    out = evaluate_research_candidacy(res)
    assert out["approved"] is False
    assert out.get("production_mutation") is False


def test_feedback_does_not_claim_production_mutation():
    res = WFAExecutor().execute(_job(experiment_id="EXP-FB2"), _bars())
    fb = feedback_experiment_to_knowledge(res)
    assert fb["production_mutation"] is False


def test_fingerprint_mutations():
    keys = [
        {"random_seed": 1},
        {"parameters": {"sma_window": 10}},
        {"dataset_hash": "other-ds"},
        {"feature_hash": "other-ft"},
        {"commit_sha": "deadbeef"},
        {"cost_model": "idx_broker_v1"},
        {"strategy_version": "9.9.9"},
    ]
    for mut in keys:
        j = _job()
        assert fingerprint_changes_when_input_changes(j, mutate=mut), mut


def test_fingerprint_ignores_wall_clock():
    j1 = _job(experiment_id="EXP-T1")
    j2 = _job(experiment_id="EXP-T1")
    assert j1.configuration_fingerprint() == j2.configuration_fingerprint()


def test_e2e_reproducibility(tmp_path):
    bars = _bars(150, seed=7)
    job = _job(experiment_id="EXP-REPRO2")
    s1 = ExperimentResultStore(tmp_path / "a")
    s2 = ExperimentResultStore(tmp_path / "b")
    r1 = WFAExecutor(store=s1).execute(job, bars)
    r2 = WFAExecutor(store=s2).execute(job, bars)
    rep = verify_reproducibility(r1, r2)
    assert rep.fingerprint_match
    assert rep.metrics_match
    assert r1.metrics["oos"]["n_trades"] == r2.metrics["oos"]["n_trades"]


def test_tamper_result_hash_after_metric_mutation():
    res = WFAExecutor().execute(_job(experiment_id="EXP-TAMP"), _bars())
    ok, _ = check_tamper(res)
    assert ok
    res.metrics = {**res.metrics, "oos": {**(res.metrics.get("oos") or {}), "expectancy": 999.0}}
    ok2, reason = check_tamper(res)
    assert ok2 is False
    assert "tamper" in reason or "stale" in reason


def test_future_feature_blocks_evidence():
    bars = _bars()
    bars["future_close"] = bars["close"].shift(-1)
    res = WFAExecutor().execute(_job(experiment_id="EXP-FUT"), bars)
    assert res.status == "INVALID"
    pkg = experiment_result_to_evidence_package(res)
    assert pkg.leakage_detected or "LOOKAHEAD" in ",".join(pkg.hard_rejects)
    out = evaluate_research_candidacy(res)
    assert out["approved"] is False


def test_unknown_dataset_blocks_provenance():
    res = WFAExecutor().execute(_job(experiment_id="EXP-UNK", dataset_hash="UNKNOWN"), _bars())
    res.dataset_hash = "UNKNOWN"
    ok, reason = check_result_provenance(res)
    assert ok is False
    assert "dataset" in reason


def test_selection_is_not_oos_tuning():
    res = WFAExecutor().execute(_job(experiment_id="EXP-SEL"), _bars())
    assert "no_oos_tuning" in res.selection_rule
    assert res.selection_split in ("NONE",)


def test_anti_overfit_blocks_insufficient():
    res = ExperimentResult(
        experiment_id="E-SMALL",
        job_id="J",
        configuration_fingerprint="abc",
        result_hash="def",
        dataset_hash="ds",
        cost_model="simulation_v2",
        seed=1,
        status="INSUFFICIENT_EVIDENCE",
        metrics={"oos": {"n_trades": 1, "expectancy": 0.1}},
        robustness={"overfit_risk": False, "n_oos_windows": 1, "n_positive_oos_windows": 1},
        selection_rule="fixed_params_from_job_no_oos_tuning",
        selection_split="NONE",
    )
    ok, reason = check_anti_overfit_gate(res)
    assert ok is False


def test_store_idempotent(tmp_path):
    bars = _bars()
    job = _job(experiment_id="EXP-IDEM")
    store = ExperimentResultStore(tmp_path)
    exe = WFAExecutor(store=store)
    r1 = exe.execute(job, bars)
    r2 = exe.execute(job, bars)
    assert r1.result_hash == r2.result_hash
    assert len(store._by_key) == 1
