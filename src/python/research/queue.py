"""Lightweight research job queue — no Celery/Airflow."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

from src.python.research.budget import ResearchBudget
from src.python.research.colab_jobs import ColabResearchJob


@dataclass
class QueueItem:
    job: ColabResearchJob
    priority: float = 0.0
    status: str = "QUEUED"
    retries: int = 0
    max_retries: int = 2

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["job"] = self.job.to_dict()
        return d


class ResearchQueue:
    def __init__(self, budget: Optional[ResearchBudget] = None):
        self.budget = budget or ResearchBudget()
        self._items: dict[str, QueueItem] = {}

    def enqueue(self, job: ColabResearchJob, *, priority: float = 0.0) -> QueueItem:
        if job.job_id in self._items:
            return self._items[job.job_id]
        if not self.budget.can_accept(budget_sec=job.budget_sec):
            item = QueueItem(job=job, priority=priority, status="BLOCKED")
            self._items[job.job_id] = item
            return item
        item = QueueItem(job=job, priority=priority, status="QUEUED")
        self._items[job.job_id] = item
        return item

    def next_job(self) -> Optional[ColabResearchJob]:
        queued = [i for i in self._items.values() if i.status == "QUEUED"]
        if not queued:
            return None
        queued.sort(key=lambda x: -x.priority)
        item = queued[0]
        item.status = "RUNNING"
        self.budget.consume(budget_sec=item.job.budget_sec)
        return item.job

    def complete(self, job_id: str, *, ok: bool = True) -> None:
        item = self._items.get(job_id)
        if not item:
            return
        item.status = "COMPLETED" if ok else "FAILED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [i.to_dict() for i in self._items.values()],
            "budget": self.budget.to_dict(),
        }
