"""EvidencePackage schema — immutable factual evidence, not promotional narrative.

evidence_origin is MANDATORY and must not be inferred.
Valid values: CORE | COLAB only.

Flow:
  Facts / Metrics / Artifacts
        ↓
  EvidencePackage (origin explicit)
        ↓
  PromotionGate
        ↓
  Authority Decision

Colab must never write final authority_decision or auto-promote.
"""
from __future__ import annotations

from typing import Any

VALID_ORIGINS = frozenset({"CORE", "COLAB"})

PROVENANCE_FIELDS = (
    "evidence_origin",
    "experiment_id",
    "experiment_version",
    "parent_experiment_id",
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

COLAB_FORBIDDEN_DECISIONS = frozenset({"APPROVED", "PROMOTED", "CHAMPION", "GO_LIVE"})


def validate_evidence_package_dict(d: dict[str, Any]) -> tuple[bool, list[str]]:
    """Hard-validate origin; soft-check provenance; reject authority leakage."""
    issues: list[str] = []
    if not d.get("strategy_id"):
        issues.append("missing strategy_id")

    origin = str(d.get("evidence_origin") or "").strip().upper()
    if not origin:
        issues.append("missing_evidence_origin")
    elif origin not in VALID_ORIGINS:
        issues.append(f"invalid_evidence_origin:{origin}")

    for k in FORBIDDEN_AUTHORITY_KEYS:
        if k in d and d[k]:
            issues.append(f"forbidden_authority_key:{k}")

    if origin == "COLAB":
        auth = str(d.get("authority_decision") or "").strip().upper()
        if auth in COLAB_FORBIDDEN_DECISIONS:
            issues.append(f"colab_cannot_set_authority_decision:{auth}")
        promo = str(d.get("promotion_status") or "").strip().upper()
        if promo in COLAB_FORBIDDEN_DECISIONS:
            issues.append(f"colab_cannot_set_promotion_status:{promo}")

    missing_prov = [f for f in ("experiment_id", "git_commit", "dataset_checksum") if not d.get(f)]
    if missing_prov:
        issues.append("provenance_incomplete:" + ",".join(missing_prov))

    hard = [i for i in issues if not i.startswith("provenance_incomplete")]
    return (len(hard) == 0, issues)


def require_origin(d: dict[str, Any]) -> str:
    """Return normalized origin or raise ValueError (fail-closed)."""
    origin = str(d.get("evidence_origin") or "").strip().upper()
    if origin not in VALID_ORIGINS:
        raise ValueError(f"evidence_origin must be CORE|COLAB, got {origin!r}")
    return origin


def experiment_registry_relpath(experiment_id: str) -> str:
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in experiment_id)[:120]
    return f"IDX/experiment_registry/{safe}/"
