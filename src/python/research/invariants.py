"""Research-plane institutional invariants — fail-closed.

All checks return (ok: bool, reason: str). Never soft-pass missing provenance.
"""
from __future__ import annotations

from typing import Any, Optional

from src.python.research.experiment_result import ExperimentResult
from src.python.strategy.evidence import EvidencePackage


BLOCK_CANDIDACY_STATUSES = frozenset({
    "PENDING", "RUNNING", "FAILED", "INVALID",
    "INSUFFICIENT_EVIDENCE", "FRAGILE",
})


def check_result_provenance(result: ExperimentResult) -> tuple[bool, str]:
    if not result.experiment_id:
        return False, "missing_experiment_id"
    if not result.job_id:
        return False, "missing_job_id"
    if not result.configuration_fingerprint:
        return False, "missing_configuration_fingerprint"
    if not result.result_hash:
        return False, "missing_result_hash"
    if result.dataset_hash in ("", "UNKNOWN", None):
        return False, "dataset_hash_unknown"
    if result.cost_model in ("", "unknown", None):
        return False, "cost_model_missing"
    if result.status in ("FAILED", "INVALID"):
        return False, f"status_{result.status}"
    return True, "ok"


def check_no_oos_tuning(result: ExperimentResult) -> tuple[bool, str]:
    rule = (result.selection_rule or "").lower()
    if "oos" in rule and "no_oos" not in rule and "not" not in rule:
        return False, "selection_rule_implies_oos_tuning"
    split = (result.selection_split or "").upper()
    if rule and "no_oos_tuning" not in rule and "fixed_params" not in rule:
        if split in ("OOS", "TEST"):
            return False, "oos_used_for_selection"
    return True, "ok"


def check_anti_overfit_gate(result: ExperimentResult) -> tuple[bool, str]:
    if result.status in BLOCK_CANDIDACY_STATUSES:
        return False, f"status_blocks_candidacy:{result.status}"
    robust = result.robustness or {}
    if robust.get("overfit_risk"):
        return False, "overfit_risk"
    oos = (result.metrics or {}).get("oos") or {}
    if int(oos.get("n_trades") or 0) < 5:
        return False, "insufficient_oos_trades"
    n_win = int(robust.get("n_oos_windows") or len(result.windows or []))
    if n_win < 2:
        return False, "insufficient_wfa_windows"
    if int(robust.get("n_positive_oos_windows") or 0) <= 1 and n_win > 1:
        return False, "single_window_edge"
    return True, "ok"


def check_evidence_package(pkg: EvidencePackage) -> tuple[bool, str]:
    if not pkg.strategy_id:
        return False, "missing_strategy_id"
    if not pkg.evidence_id:
        return False, "missing_evidence_id"
    if not pkg.cost_model or pkg.cost_model == "unknown":
        return False, "cost_model_missing"
    if pkg.leakage_detected or not pkg.lookahead_safe:
        return False, "leakage_detected"
    if pkg.hard_rejects:
        return False, f"hard_rejects:{','.join(pkg.hard_rejects[:3])}"
    if not pkg.oos_evaluated:
        return False, "oos_not_evaluated"
    if pkg.oos_n_trades < 5:
        return False, "insufficient_oos_trades"
    if not pkg.reproducible:
        return False, "not_reproducible"
    return True, "ok"


def check_tamper(
    result: ExperimentResult,
    *,
    expected_fingerprint: Optional[str] = None,
    expected_result_hash: Optional[str] = None,
) -> tuple[bool, str]:
    if expected_fingerprint and result.configuration_fingerprint != expected_fingerprint:
        return False, "fingerprint_mismatch"
    recomputed = result.compute_hash()
    if expected_result_hash and result.result_hash != expected_result_hash:
        return False, "result_hash_mismatch"
    if result.result_hash and result.result_hash != recomputed:
        return False, "result_hash_stale_or_tampered"
    return True, "ok"


def assert_research_cannot_promote(decision: dict[str, Any]) -> None:
    if decision.get("approved") is True and decision.get("research_path"):
        raise PermissionError("research_path_cannot_set_approved")
    if decision.get("production_mutation") is True:
        raise PermissionError("research_path_cannot_mutate_production")
