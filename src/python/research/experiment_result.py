"""Immutable ExperimentResult artifacts — research plane only."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


RESULT_STATUSES = (
    "PENDING", "RUNNING", "COMPLETED", "FAILED", "INVALID",
    "INSUFFICIENT_EVIDENCE", "ROBUST", "FRAGILE",
)


@dataclass
class ExperimentResult:
    experiment_id: str
    job_id: str
    hypothesis_id: str = ""
    baseline_version: str = "rule_sma20@1.0"
    challenger_version: str = ""
    dataset_hash: str = "UNKNOWN"
    feature_hash: str = "UNKNOWN"
    commit_sha: str = "UNKNOWN"
    cost_model: str = "simulation_v2"
    cost_model_detail: dict[str, Any] = field(default_factory=dict)
    seed: int = 42
    configuration_fingerprint: str = ""
    windows: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    robustness: dict[str, Any] = field(default_factory=dict)
    regime_results: list[dict[str, Any]] = field(default_factory=list)
    leakage_checks: dict[str, Any] = field(default_factory=dict)
    integrity_checks: dict[str, Any] = field(default_factory=dict)
    status: str = "PENDING"
    number_of_trials: int = 1
    number_of_candidates: int = 1
    selection_rule: str = "single_challenger"
    selection_split: str = "OOS"
    created_at: str = ""
    result_hash: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        if self.status not in RESULT_STATUSES:
            raise ValueError(f"invalid_status:{self.status}")
        if not self.result_hash:
            self.result_hash = self.compute_hash()

    def compute_hash(self) -> str:
        payload = {
            "experiment_id": self.experiment_id,
            "job_id": self.job_id,
            "configuration_fingerprint": self.configuration_fingerprint,
            "dataset_hash": self.dataset_hash,
            "feature_hash": self.feature_hash,
            "commit_sha": self.commit_sha,
            "cost_model": self.cost_model,
            "seed": self.seed,
            "metrics": self.metrics,
            "status": self.status,
        }
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ExperimentResultStore:
    """Append-only store keyed by experiment_id + configuration_fingerprint."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else None
        self._by_key: dict[str, ExperimentResult] = {}
        if self.root:
            self.root.mkdir(parents=True, exist_ok=True)
            self._load()

    def _key(self, experiment_id: str, fingerprint: str) -> str:
        return f"{experiment_id}::{fingerprint}"

    def _load(self) -> None:
        if not self.root:
            return
        for p in self.root.glob("**/experiment_result.json"):
            try:
                row = json.loads(p.read_text())
                er = ExperimentResult(**{
                    k: row[k] for k in ExperimentResult.__dataclass_fields__ if k in row
                })
                self._by_key[self._key(er.experiment_id, er.configuration_fingerprint)] = er
            except Exception:
                continue

    def get(self, experiment_id: str, fingerprint: str) -> Optional[ExperimentResult]:
        return self._by_key.get(self._key(experiment_id, fingerprint))

    def put(self, result: ExperimentResult) -> ExperimentResult:
        """Idempotent: same key returns existing immutable result."""
        key = self._key(result.experiment_id, result.configuration_fingerprint)
        existing = self._by_key.get(key)
        if existing is not None:
            return existing
        self._by_key[key] = result
        if self.root:
            dest = self.root / result.experiment_id
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "experiment_result.json").write_text(
                json.dumps(result.to_dict(), indent=2, default=str)
            )
        return result
