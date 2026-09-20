"""EvidencePackage nested immutability after freeze."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.python.research.colab_jobs import ResearchJobKind, make_job
from src.python.research.evidence_bridge import experiment_result_to_evidence_package
from src.python.research.wfa_executor import WFAExecutor
from src.python.strategy.evidence_freeze import FrozenMutationError, deep_freeze


def _bars(n=120, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.1, n)
    return pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=n, freq="B"),
        "symbol": "BBCA", "open": open_, "high": close + 1, "low": close - 1,
        "close": close, "volume": rng.integers(1e5, 1e6, n),
    })


def test_nested_notes_append_rejected():
    job = make_job(job_id="J", kind=ResearchJobKind.WALK_FORWARD, experiment_id="E", strategy_id="s",
                   dataset_hash="d", parameters={"sma_window": 20, "n_windows": 3})
    res = WFAExecutor().execute(job, _bars())
    pkg = experiment_result_to_evidence_package(res)
    with pytest.raises(FrozenMutationError):
        pkg.notes.append("tamper")


def test_nested_hard_rejects_mutation_rejected():
    job = make_job(job_id="J2", kind=ResearchJobKind.WALK_FORWARD, experiment_id="E2", strategy_id="s",
                   dataset_hash="d", parameters={"sma_window": 20, "n_windows": 3})
    pkg = experiment_result_to_evidence_package(WFAExecutor().execute(job, _bars(seed=2)))
    with pytest.raises(FrozenMutationError):
        pkg.hard_rejects.append("FAKE")


def test_nested_window_mutation_rejected():
    job = make_job(job_id="J3", kind=ResearchJobKind.WALK_FORWARD, experiment_id="E3", strategy_id="s",
                   dataset_hash="d", parameters={"sma_window": 20, "n_windows": 3})
    pkg = experiment_result_to_evidence_package(WFAExecutor().execute(job, _bars(seed=3)))
    if pkg.wf_windows:
        with pytest.raises(FrozenMutationError):
            pkg.wf_windows.append({"window_id": "TAMPER"})
        w0 = pkg.wf_windows[0]
        if isinstance(w0, dict):
            with pytest.raises(FrozenMutationError):
                w0["expectancy"] = 999.0


def test_deep_freeze_dict():
    d = deep_freeze({"a": 1, "b": {"c": 2}})
    with pytest.raises(FrozenMutationError):
        d["a"] = 9
    with pytest.raises(FrozenMutationError):
        d["b"]["c"] = 9
