"""Immutable promotion audit log.

Each promotion is a versioned record. Changing strategy_version requires a NEW
evidence evaluation and a NEW promotion record — never mutate historical rows.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.python.strategy.promotion_gate import (
    PromotionDecision,
    assert_promoted_invariants,
    promoted_record_missing_fields,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class PromotionAuditRecord:
    """Frozen audit row — identity is (strategy_id, strategy_version, evidence_id, promotion_id)."""
    strategy_id: str
    strategy_version: str
    evidence_id: str
    promotion_id: str
    authority_id: str
    dataset_hash: str
    feature_hash: str
    cost_model: str
    baseline_id: str
    lifecycle_status: str
    evaluation_date: str
    recorded_at: str
    reason: str = ""
    notes: tuple[str, ...] = ()

    def key(self) -> tuple[str, str, str, str]:
        return (self.strategy_id, self.strategy_version, self.evidence_id, self.promotion_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_decision(cls, decision: PromotionDecision) -> "PromotionAuditRecord":
        assert_promoted_invariants(decision)
        return cls(
            strategy_id=decision.strategy_id,
            strategy_version=decision.strategy_version,
            evidence_id=decision.evidence_id,
            promotion_id=decision.promotion_id,
            authority_id=decision.authority_id,
            dataset_hash=decision.dataset_hash,
            feature_hash=decision.feature_hash,
            cost_model=decision.cost_model,
            baseline_id=decision.baseline_id,
            lifecycle_status=decision.lifecycle_status,
            evaluation_date=decision.evaluation_date,
            recorded_at=_now_iso(),
            reason=decision.reason,
            notes=tuple(decision.notes),
        )


class PromotionAuditLog:
    """Append-only promotion history. Updates to existing keys are rejected."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self._records: list[PromotionAuditRecord] = []
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        data = json.loads(self.path.read_text())
        for row in data.get("records", []):
            notes = row.get("notes") or []
            self._records.append(PromotionAuditRecord(
                strategy_id=row["strategy_id"],
                strategy_version=row["strategy_version"],
                evidence_id=row["evidence_id"],
                promotion_id=row["promotion_id"],
                authority_id=row["authority_id"],
                dataset_hash=row.get("dataset_hash", ""),
                feature_hash=row.get("feature_hash", ""),
                cost_model=row.get("cost_model", ""),
                baseline_id=row.get("baseline_id", ""),
                lifecycle_status=row.get("lifecycle_status", "PROMOTED"),
                evaluation_date=row.get("evaluation_date", ""),
                recorded_at=row.get("recorded_at", ""),
                reason=row.get("reason", ""),
                notes=tuple(notes),
            ))

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [r.to_dict() for r in self._records], "immutable": True}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def keys(self) -> set[tuple[str, str, str, str]]:
        return {r.key() for r in self._records}

    def append(self, decision: PromotionDecision) -> PromotionAuditRecord:
        """Append a PROMOTED decision. Refuses overwrite of existing identity."""
        missing = promoted_record_missing_fields(decision)
        if missing:
            raise RuntimeError(f"cannot_audit_incomplete_promotion missing={missing}")
        rec = PromotionAuditRecord.from_decision(decision)
        if rec.key() in self.keys():
            raise RuntimeError(
                f"immutable_violation: promotion record already exists for {rec.key()}. "
                f"Bump strategy_version / evidence_id for a new evaluation."
            )
        for existing in self._records:
            if (
                existing.strategy_id == rec.strategy_id
                and existing.strategy_version == rec.strategy_version
                and existing.promotion_id == rec.promotion_id
            ):
                raise RuntimeError(
                    f"immutable_violation: strategy_version={rec.strategy_version} "
                    f"already bound to promotion_id={rec.promotion_id}"
                )
        self._records.append(rec)
        self._save()
        return rec

    def list_for_strategy(self, strategy_id: str) -> list[PromotionAuditRecord]:
        return [r for r in self._records if r.strategy_id == strategy_id]

    def latest(self, strategy_id: str) -> Optional[PromotionAuditRecord]:
        rows = self.list_for_strategy(strategy_id)
        return rows[-1] if rows else None

    def to_dict(self) -> dict[str, Any]:
        return {"records": [r.to_dict() for r in self._records], "immutable": True}
