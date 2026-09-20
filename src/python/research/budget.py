"""Research budget governor — Actions=CHEAP only; Colab may use MEDIUM/HEAVY."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ResearchBudget:
    max_jobs_per_cycle: int = 5
    max_runtime_per_job_sec: int = 1200
    max_candidates: int = 5
    max_trials: int = 20
    max_total_research_budget_sec: int = 3600
    used_sec: int = 0
    used_jobs: int = 0

    def can_accept(self, *, budget_sec: int = 0, resource_class: str = "CHEAP") -> bool:
        if self.used_jobs >= self.max_jobs_per_cycle:
            return False
        if self.used_sec + budget_sec > self.max_total_research_budget_sec:
            return False
        if budget_sec > self.max_runtime_per_job_sec:
            return False
        if resource_class == "HEAVY" and self.max_runtime_per_job_sec < 600:
            return False
        return True

    def consume(self, *, budget_sec: int) -> None:
        self.used_jobs += 1
        self.used_sec += int(budget_sec)

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_jobs_per_cycle": self.max_jobs_per_cycle,
            "max_runtime_per_job_sec": self.max_runtime_per_job_sec,
            "max_total_research_budget_sec": self.max_total_research_budget_sec,
            "used_sec": self.used_sec,
            "used_jobs": self.used_jobs,
            "remaining_jobs": max(0, self.max_jobs_per_cycle - self.used_jobs),
        }
