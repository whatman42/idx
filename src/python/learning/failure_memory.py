"""Failure Memory — operational error intelligence (not chat memory)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from src.python.learning.attribution import attribute_episode
from src.python.learning.contracts import FailureRecord, LearningStatus, SignalEpisode


class FailureMemory:
    """Stores failure episodes and pattern stats. Changes stay OBSERVED until experiment."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self._records: list[FailureRecord] = []
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        data = json.loads(self.path.read_text())
        for row in data.get("records", []):
            self._records.append(FailureRecord(**{
                k: row[k] for k in FailureRecord.__dataclass_fields__ if k in row
            }))

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [r.to_dict() for r in self._records]}
        self.path.write_text(json.dumps(payload, indent=2))

    def observe(self, ep: SignalEpisode, failure_id: str) -> Optional[FailureRecord]:
        if float(ep.r_multiple or 0.0) >= -0.1 and ep.outcome not in ("LOSS",):
            return None
        attr = attribute_episode(ep)
        root = attr.root_cause_candidates[0] if attr.root_cause_candidates else "UNKNOWN"
        similar = self._similar_count(ep.strategy_id, ep.regime, root)
        rate = self._failure_rate(ep.strategy_id, ep.regime)
        pattern = ";".join(attr.notes[:3]) if attr.notes else root
        action = f"penalty {ep.strategy_id} on regime {ep.regime}" if rate > 0.5 else "monitor"
        rec = FailureRecord(
            failure_id=failure_id,
            episode_id=ep.episode_id,
            regime=ep.regime,
            strategy_id=ep.strategy_id,
            signal="BUY" if ep.side > 0 else "HOLD",
            r_multiple=float(ep.r_multiple or 0.0),
            root_cause=root,
            similar_count=similar,
            historical_failure_rate=rate,
            pattern=pattern,
            status=LearningStatus.OBSERVED.value,
            proposed_action=action,
        )
        self._records.append(rec)
        self._save()
        return rec

    def _similar_count(self, strategy_id: str, regime: str, root: str) -> int:
        return sum(
            1 for r in self._records
            if r.strategy_id == strategy_id and r.regime == regime and r.root_cause == root
        )

    def _failure_rate(self, strategy_id: str, regime: str) -> float:
        rows = [r for r in self._records if r.strategy_id == strategy_id and r.regime == regime]
        if not rows:
            return 0.0
        losses = sum(1 for r in rows if r.r_multiple < 0)
        return losses / len(rows)

    def list_observed(self) -> list[FailureRecord]:
        return [r for r in self._records if r.status == LearningStatus.OBSERVED.value]

    def to_dict(self) -> dict[str, Any]:
        return {"records": [r.to_dict() for r in self._records], "count": len(self._records)}
