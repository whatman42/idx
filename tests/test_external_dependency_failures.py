"""Adversarial tests: external failure ≠ success ≠ promotion ≠ ledger mutation."""
from __future__ import annotations

from src.python.external.adapters import (
    probe_colab_available,
    probe_drive_artifact,
    probe_llm,
    probe_market_data,
    probe_memory,
    report_colab_job_outcome,
    safe_external_call,
)
from src.python.external.gate import evaluate_research_job_readiness, fail_closed_promotion_on_deps
from src.python.external.inventory import inventory_table
from src.python.external.states import (
    DependencyKind,
    DependencyReport,
    DependencyStatus,
    ResearchJobDependencyState,
    classify_exception,
)
from src.python.memory.client import MemoryStatus, ResearchMemory


def test_inventory_non_empty():
    inv = inventory_table()
    assert len(inv) >= 5
    for row in inv:
        assert row["can_affect_ledger"] is False
        assert row["can_promote"] is False


def test_classify_timeout():
    r = classify_exception(TimeoutError("read timed out"), kind=DependencyKind.COMPUTE)
    assert r.status == DependencyStatus.TIMEOUT.value
    assert r.can_retry is True


def test_classify_auth():
    r = classify_exception(PermissionError("unauthorized 401"), kind=DependencyKind.MEMORY)
    assert r.status == DependencyStatus.AUTH_ERROR.value
    assert r.can_retry is False


def test_secret_scrubbed_from_message():
    r = classify_exception(RuntimeError("token=supersecret123 failed"), kind=DependencyKind.OTHER)
    assert "supersecret" not in r.message


def test_turso_unavailable_not_success():
    m = ResearchMemory(status=MemoryStatus.UNAVAILABLE, last_error="down")
    r = probe_memory(m)
    assert r.status == DependencyStatus.UNAVAILABLE.value
    out = m.upsert_experiment({"experiment_id": "X", "fingerprint": "Y"})
    assert out["ok"] is False


def test_memory_write_unavailable_not_ok():
    m = ResearchMemory(status=MemoryStatus.UNAVAILABLE)
    assert m.upsert_experiment({"experiment_id": "a", "fingerprint": "b"})["ok"] is False


def test_drive_missing_artifact():
    r = probe_drive_artifact(available=False)
    assert r.status == DependencyStatus.ARTIFACT_MISSING.value


def test_drive_checksum_corrupt():
    r = probe_drive_artifact(available=True, checksum_ok=False)
    assert r.status == DependencyStatus.ARTIFACT_CORRUPT.value


def test_drive_auth_failure():
    r = probe_drive_artifact(available=False, auth_ok=False)
    assert r.status == DependencyStatus.AUTH_ERROR.value


def test_colab_incomplete_not_available():
    r = report_colab_job_outcome(completed=False)
    assert r.status != DependencyStatus.AVAILABLE.value


def test_colab_timeout():
    r = report_colab_job_outcome(completed=False, timeout=True)
    assert r.status == DependencyStatus.TIMEOUT.value
    assert r.can_retry is True


def test_colab_missing_output_hash():
    r = report_colab_job_outcome(completed=True, artifact_present=False, result_hash="")
    assert r.status == DependencyStatus.ARTIFACT_MISSING.value


def test_llm_unavailable():
    r = probe_llm(available=False)
    assert r.status == DependencyStatus.UNAVAILABLE.value
    assert r.meta.get("fabricated") is False


def test_data_stale_blocks():
    r = probe_market_data(rows=100, stale=True)
    assert r.status == DependencyStatus.DATA_STALE.value
    assert r.required is True


def test_data_invalid_empty():
    r = probe_market_data(rows=0)
    assert r.status == DependencyStatus.DATA_INVALID.value


def test_composite_success_only_when_required_ok():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="AVAILABLE", required=True)
    state.compute = DependencyReport(kind="COMPUTE", status="AVAILABLE", required=True)
    state.memory = DependencyReport(kind="MEMORY", status="UNAVAILABLE", required=False)
    state.llm = DependencyReport(kind="LLM", status="UNAVAILABLE", required=False)
    evaluate_research_job_readiness(state)
    assert state.job_status == "DEGRADED"


def test_composite_blocked_when_data_stale():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="DATA_STALE", required=True)
    state.compute = DependencyReport(kind="COMPUTE", status="AVAILABLE", required=True)
    evaluate_research_job_readiness(state)
    assert state.job_status in ("BLOCKED", "FAILED")


def test_composite_failed_on_corrupt_artifact_required():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="AVAILABLE", required=True)
    state.compute = DependencyReport(kind="COMPUTE", status="AVAILABLE", required=True)
    state.artifact = DependencyReport(kind="ARTIFACT", status="ARTIFACT_CORRUPT", required=True)
    evaluate_research_job_readiness(state)
    assert state.job_status == "FAILED"


def test_promotion_fail_closed_on_blocked_deps():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="DATA_INVALID", required=True)
    state.compute = DependencyReport(kind="COMPUTE", status="AVAILABLE", required=True)
    out = fail_closed_promotion_on_deps(state, evidence_ok=True)
    assert out["approved"] is False
    assert out["candidacy"] is False
    assert out["production_mutation"] is False


def test_promotion_fail_closed_even_when_deps_ok_without_evidence():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="AVAILABLE", required=True)
    state.compute = DependencyReport(kind="COMPUTE", status="AVAILABLE", required=True)
    out = fail_closed_promotion_on_deps(state, evidence_ok=False)
    assert out["approved"] is False
    assert out["candidacy"] is False


def test_promotion_candidacy_only_not_approved():
    state = ResearchJobDependencyState()
    state.data = DependencyReport(kind="DATA", status="AVAILABLE", required=True)
    state.compute = DependencyReport(kind="COMPUTE", status="AVAILABLE", required=True)
    out = fail_closed_promotion_on_deps(state, evidence_ok=True)
    assert out["candidacy"] is True
    assert out["approved"] is False


def test_safe_external_call_no_false_success():
    def boom():
        raise ConnectionError("network down")
    out, rep = safe_external_call(boom, kind=DependencyKind.DATA, required=True)
    assert out is None
    assert rep.status == DependencyStatus.NETWORK_ERROR.value
    assert rep.required is True


def test_dependency_state_never_affects_ledger_flag():
    state = ResearchJobDependencyState()
    d = state.to_dict()
    assert d["affects_ledger"] is False
    assert d["affects_champion"] is False
