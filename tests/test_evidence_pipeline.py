"""EvidencePackage bridge, reproducibility, anti-overfit, PromotionGate candidacy."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.python.research.colab_jobs import ResearchJobKind, make_job
from src.python.research.evidence_bridge import (
    evaluate_research_candidacy,
    experiment_result_to_evidence,
    experiment_result_to_evidence_package,
)
from src.python.research.experiment_result import ExperimentResultStore
from src.python.research.feedback import feedback_experiment_to_knowledge
from src.python.research.reproducibility import (
    fingerprint_changes_when_input_changes,
    verify_reproducibility,
)
from src.python.research.wfa_executor import WFAExecutor
from src.python.strategy.evidence import EvidencePackage, HardRejectCode


def _bars(n: int = 150, seed: int = 7) -> pd.DataFrame:
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
        job_id="J-EV",
        kind=ResearchJobKind.WALK_FORWARD,
        experiment_id="EXP-EV",
        strategy_id="rule_sma20",
        parameters={"sma_window": 20, "n_windows": 3},
        dataset_hash="synth-v1",
        feature_hash="feat-v1",
        commit_sha="abc123",
        random_seed=7,
    )
    base.update(kw)
    return make_job(**base)


def test_experiment_result_becomes_evidence_package():
    res = WFAExecutor().execute(_job(), _bars())
    pkg = experiment_result_to_evidence_package(res)
    assert isinstance(pkg, EvidencePackage)
    assert pkg.evidence_id.startswith("EVD-")
    assert pkg.oos_evaluated is True
    assert pkg.cost_model == "simulation_v2"
    assert pkg.timing == "signal_T_execute_open_Tplus1"
    assert "auto_promote=false" in " ".join(pkg.notes)
    d = pkg.to_promotion_evidence()
    assert d["evidence_id"] == pkg.evidence_id
    assert "out_of_sample" in d
    assert "walk_forward" in d


def test_promotion_gate_candidacy_never_approved():
    res = WFAExecutor().execute(_job(experiment_id="EXP-CAND"), _bars())
    out = evaluate_research_candidacy(res)
    assert out["approved"] is False
    assert out["production_mutation"] is False
    assert out.get("research_path") is True


def test_lookahead_maps_to_hard_reject():
    bars = _bars()
    bars["future_return"] = bars["close"].shift(-1)
    res = WFAExecutor().execute(_job(experiment_id="EXP-LA"), bars)
    pkg = experiment_result_to_evidence_package(res)
    assert HardRejectCode.LOOKAHEAD_DETECTED.value in pkg.hard_rejects
    assert pkg.leakage_detected is True
    assert pkg.lookahead_safe is False


def test_reproducibility_same_inputs_equivalent(tmp_path):
    bars = _bars(150, seed=7)
    job = _job(experiment_id="EXP-REPRO")
    store = ExperimentResultStore(tmp_path)
    exe = WFAExecutor(store=store)
    r1 = exe.execute(job, bars)
    store2 = ExperimentResultStore(tmp_path)
    r2 = WFAExecutor(store=store2).execute(job, bars)
    report = verify_reproducibility(r1, r2)
    assert report.fingerprint_match
    assert report.result_hash_match
    assert report.equivalent


def test_fingerprint_changes_when_seed_or_params_change():
    j = _job()
    assert fingerprint_changes_when_input_changes(j, mutate={"random_seed": 99})
    j2 = _job()
    assert fingerprint_changes_when_input_changes(j2, mutate={"parameters": {"sma_window": 15}})
    j3 = _job()
    assert fingerprint_changes_when_input_changes(j3, mutate={"dataset_hash": "other"})


def test_anti_overfit_selection_is_oos_not_tuned():
    res = WFAExecutor().execute(_job(experiment_id="EXP-OF"), _bars())
    assert res.selection_split == "OOS"
    assert "no_oos_tuning" in res.selection_rule
    assert res.robustness.get("selection_rule") == "fixed_params_from_job_no_oos_tuning"
    assert res.number_of_trials >= 1


def test_evidence_dict_has_selection_metadata():
    res = WFAExecutor().execute(_job(experiment_id="EXP-META"), _bars())
    d = experiment_result_to_evidence(res)
    assert d["selection_split"] == "OOS"
    assert d["auto_promote"] is False
    assert d["approved"] is False
    assert d.get("configuration_fingerprint")


def test_feedback_to_knowledge_advisory_only():
    res = WFAExecutor().execute(_job(experiment_id="EXP-FB"), _bars())
    out = feedback_experiment_to_knowledge(res)
    assert out["ok"] is True
    assert out["production_mutation"] is False
