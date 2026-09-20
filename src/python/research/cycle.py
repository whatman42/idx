"""Research cycle — weekly/threshold path on top of LearningLoop.

Daily (cheap / Actions): observe, attribute, drift, failure memory
Weekly / threshold (orchestrated here): factory batch → Colab job specs
Promotion: still requires EvidencePackage → PromotionGate → Authority
"""
from __future__ import annotations

from typing import Any, Optional

from src.python.learning.contracts import SignalEpisode
from src.python.learning.integrity import gate_learning_on_integrity, reconcile_episode_pnl
from src.python.learning.loop import LearningLoop
from src.python.research.colab_jobs import ResearchJobKind, jobs_from_experiment_ids
from src.python.research.factory import ResearchFactory
from src.python.research.regime_matrix import RegimeMatrix


class ResearchCycle:
    """Coordinates learning observe + research factory + Colab job specs."""

    def __init__(
        self,
        *,
        learning: Optional[LearningLoop] = None,
        factory: Optional[ResearchFactory] = None,
        regime_matrix: Optional[RegimeMatrix] = None,
    ):
        self.learning = learning or LearningLoop()
        self.regime_matrix = regime_matrix or RegimeMatrix()
        self.factory = factory or ResearchFactory(
            knowledge=self.learning.knowledge,
            ledger=self.learning.experiments,
            regime_matrix=self.regime_matrix,
        )

    def ingest_episodes(self, episodes: list[SignalEpisode]) -> dict[str, Any]:
        observations = []
        for ep in episodes:
            observations.append(self.learning.observe_episode(ep))
            self.regime_matrix.observe(ep)
        integrity = reconcile_episode_pnl(self.learning.episodes)
        gate = gate_learning_on_integrity(integrity)
        return {
            "n_observed": len(observations),
            "integrity": integrity.to_dict(),
            "learning_gate": gate,
            "regime_matrix": self.regime_matrix.to_dict(),
        }

    def run_research_batch(
        self,
        *,
        experiment_evidence: Optional[dict[str, Any]] = None,
        emit_colab_jobs: bool = True,
    ) -> dict[str, Any]:
        """Generate hypotheses/experiments. Optionally attach Colab job specs.

        If integrity gate is BLOCKED, research batch is skipped.
        """
        integrity = reconcile_episode_pnl(self.learning.episodes)
        gate = gate_learning_on_integrity(integrity)
        if gate.get("learning_update") == "BLOCKED":
            return {
                "status": "BLOCKED",
                "reason": "LEARNING_DATA_INTEGRITY_FAIL",
                "gate": gate,
                "batch": None,
                "colab_jobs": [],
                "production_mutation": False,
            }

        failures = self.learning.failures.list_observed()
        # Rebuild regime matrix from SSOT episodes (idempotent; no double-count)
        self.regime_matrix.rebuild(self.learning.episodes)
        self.factory.regime_matrix = self.regime_matrix
        batch = self.factory.build_batch(
            failures=failures,
            episodes=None,  # already reconciled into regime_matrix
        )
        colab_jobs = []
        if emit_colab_jobs and batch.experiment_ids:
            for job in jobs_from_experiment_ids(
                batch.experiment_ids,
                kind=ResearchJobKind.WALK_FORWARD,
            ):
                colab_jobs.append(job.to_dict())

        candidacy = []
        if experiment_evidence:
            from src.python.learning.experiment import evaluate_experiment_to_candidacy
            for exp in self.learning.experiments.list_all():
                if exp.experiment_id in batch.experiment_ids:
                    result = evaluate_experiment_to_candidacy(exp, experiment_evidence)
                    candidacy.append(result)
                    assert result.get("approved") is False

        return {
            "status": "OK",
            "batch": batch.to_dict(),
            "colab_jobs": colab_jobs,
            "experiment_candidacy": candidacy,
            "production_mutation": False,
            "promotion_path": "EvidencePackage→PromotionGate→Authority",
            "principle": "AI may propose; only authority promotes Champion",
        }
