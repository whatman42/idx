"""Residual risks: UNAVAILABLE≠NO_MATCH, Colab per-job, no false success."""
from __future__ import annotations

from src.python.external.adapters import (
    probe_drive_artifact,
    probe_llm,
    probe_market_data,
)
from src.python.external.gate import (
    apply_job_requirements,
    evaluate_research_job_readiness,
    fail_closed_promotion_on_deps,
)
from src.python.external.states import DependencyReport, ResearchJobDependencyState
from src.python.memory.client import MemoryStatus, ResearchMemory, connect_sqlite


def test_turso_read_unavailable_not_no_match():
    m = ResearchMemory(status=MemoryStatus.UNAVAILABLE)
    q = m.query_experiment("E-1")
    assert q["status"] == "MEMORY_UNAVAILABLE"
    assert q["status"] != "NO_MATCH"
    assert q["persisted"] is False


def test_turso_read_no_match_when_available(tmp_path):
    m = connect_sqlite(tmp_path / "r.db")
    q = m.query_experiment("MISSING")
    assert q["status"] == "NO_MATCH"
    assert q["match"] is False


def test_turso_write_failed_not_persisted():
    m = ResearchMemory(status=MemoryStatus.UNAVAILABLE)
    w = m.write_experiment({"experiment_id": "X", "fingerprint": "Y"})
    assert w["persisted"] is False
    assert w["status"] == "MEMORY_UNAVAILABLE"


def test_turso_write_success_and_idempotent_retry(tmp_path):
    m = connect_sqlite(tmp_path / "w.db")
    row = {"experiment_id": "E1", "fingerprint": "fp1", "status": "COMPLETED", "result_hash": "rh"}
    w1 = m.write_experiment(row)
    w2 = m.write_experiment(row)
    assert w1["persisted"] is True
    assert w1["status"] == "MEMORY_WRITE_SUCCESS"
    assert w2["idempotent"] is True
    assert len(m.list_recent_experiments()) == 1


def test_fingerprint_unavailable_not_no_match():
    m = ResearchMemory(status=MemoryStatus.UNAVAILABLE)
    q = m.query_by_fingerprint("fp-x")
    assert q["status"] == "MEMORY_UNAVAILABLE"


def test_colab_unavailable_lightweight_continues():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="AVAILABLE", required=True)
    state.compute = DependencyReport(kind="COMPUTE", status="UNAVAILABLE", required=False)
    apply_job_requirements(state, requires_colab=False, requires_data=True)
    evaluate_research_job_readiness(state)
    assert state.job_status in ("SUCCESS", "DEGRADED")
    assert state.job_status != "BLOCKED"


def test_colab_unavailable_heavy_blocks():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="AVAILABLE", required=True)
    state.compute = DependencyReport(kind="COMPUTE", status="UNAVAILABLE", required=True)
    state.compute.required = True
    evaluate_research_job_readiness(state)
    assert state.job_status == "BLOCKED"


def test_drive_optional_failure_degraded():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="AVAILABLE", required=True)
    state.compute = DependencyReport(kind="COMPUTE", status="AVAILABLE", required=False)
    state.artifact = probe_drive_artifact(available=False)
    state.artifact.required = False
    evaluate_research_job_readiness(state)
    assert state.job_status == "DEGRADED"


def test_drive_required_failure_blocked():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="AVAILABLE", required=True)
    state.artifact = probe_drive_artifact(available=False)
    state.artifact.required = True
    evaluate_research_job_readiness(state)
    assert state.job_status == "BLOCKED"


def test_llm_failure_does_not_fabricate_approval():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="AVAILABLE", required=True)
    state.llm = probe_llm(available=False)
    state.llm.required = False
    evaluate_research_job_readiness(state)
    out = fail_closed_promotion_on_deps(state, evidence_ok=True)
    assert out["approved"] is False


def test_stale_data_blocks():
    state = ResearchJobDependencyState()
    state.data = probe_market_data(rows=50, stale=True)
    state.data.required = True
    evaluate_research_job_readiness(state)
    assert state.job_status in ("BLOCKED", "FAILED")


def test_external_failure_cannot_promote():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="NETWORK_ERROR", required=True)
    out = fail_closed_promotion_on_deps(state, evidence_ok=True)
    assert out["approved"] is False
    assert out["candidacy"] is False
    assert out["production_mutation"] is False


def test_state_flags_no_ledger_champion():
    d = ResearchJobDependencyState().to_dict()
    assert d["affects_ledger"] is False
    assert d["affects_champion"] is False


def test_no_secret_in_classify():
    from src.python.external.states import DependencyKind, classify_exception
    r = classify_exception(RuntimeError("Bearer SECRETTOKEN abc"), kind=DependencyKind.OTHER)
    assert "SECRETTOKEN" not in r.message
