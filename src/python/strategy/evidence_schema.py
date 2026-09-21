"""EvidencePackage schema — immutable factual evidence, not promotional narrative.

Flow:
  Facts / Metrics / Artifacts
        ↓
  EvidencePackage
        ↓
  PromotionGate
        ↓
  Authority Decision

Colab must never auto-promote from narrative scores.
"""
from __future__ import annotations

from typing import Any

PROVENANCE_FIELDS = (
    "experiment_id",
    "experiment_version",
    "git_commit",
    "dataset_id",
    "dataset_version",
    "dataset_checksum",
    "feature_snapshot_version",
    "code_environment",
    "dependency_lock_hash",
    "random_seed",
    "experiment_timestamp",
    "timezone",
    "train_period",
    "validation_period",
    "oos_period",
    "strategy_version",
    "model_version",
    "transaction_cost_model",
    "slippage_model",
    "sample_count",
    "artifact_manifest",
    "artifact_checksums",
    "reproducibility_status",
    "data_quality_status",
    "leakage_check_status",
)

FORBIDDEN_AUTHORITY_KEYS = (
    "auto_promote",
    "promoted",
    "champion",
    "go_live",
    "broker_execute",
)


def validate_evidence_package_dict(d: dict[str, Any]) -> tuple[bool, list[str]]:
    """Soft schema check: identity present, no authority leakage keys."""
    issues: list[str] = []
    if not d.get("strategy_id"):
        issues.append("missing strategy_id")
    for k in FORBIDDEN_AUTHORITY_KEYS:
        if k in d and d[k]:
            issues.append(f"forbidden_authority_key:{k}")
    missing_prov = [f for f in ("experiment_id", "git_commit", "dataset_checksum") if not d.get(f)]
    if missing_prov:
        issues.append("provenance_incomplete:" + ",".join(missing_prov))
    return (len([i for i in issues if not i.startswith("provenance_incomplete")]) == 0, issues)


def experiment_registry_relpath(experiment_id: str) -> str:
    """Drive-relative path for experiment registry entries (research plane only)."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in experiment_id)[:120]
    return f"IDX/experiment_registry/{safe}/"
