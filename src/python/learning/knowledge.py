"""Evidence-based knowledge base — structured memory of hypotheses/experiments."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from src.python.learning.contracts import Hypothesis, LearningStatus


class KnowledgeBase:
    """Stores hypothesis knowledge; not conversational LLM memory."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self._items: dict[str, dict[str, Any]] = {}
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        data = json.loads(self.path.read_text())
        self._items = dict(data.get("items", {}))

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"items": self._items}, indent=2))

    def upsert_hypothesis(self, h: Hypothesis) -> dict[str, Any]:
        row = {
            "hypothesis_id": h.hypothesis_id,
            "statement": h.statement,
            "regimes": list(h.regimes),
            "strategies": list(h.strategies),
            "evidence": h.evidence_count,
            "validation": {"walk_forward": False, "out_of_sample": False},
            "status": h.status,
            "counter_hypothesis": h.counter_hypothesis,
        }
        self._items[h.hypothesis_id] = row
        self._save()
        return row

    def mark_validated(self, hypothesis_id: str, *, walk_forward: bool, oos: bool) -> None:
        if hypothesis_id not in self._items:
            raise KeyError(hypothesis_id)
        self._items[hypothesis_id]["validation"] = {
            "walk_forward": walk_forward,
            "out_of_sample": oos,
        }
        if walk_forward and oos:
            self._items[hypothesis_id]["status"] = LearningStatus.VALIDATED.value
        self._save()

    def get(self, hypothesis_id: str) -> Optional[dict[str, Any]]:
        return self._items.get(hypothesis_id)

    def already_tried(self, statement_substr: str) -> list[dict[str, Any]]:
        s = statement_substr.lower()
        return [v for v in self._items.values() if s in str(v.get("statement", "")).lower()]

    def to_dict(self) -> dict[str, Any]:
        return {"items": dict(self._items)}
