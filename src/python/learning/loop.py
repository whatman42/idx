"""Learning Loop orchestrator — OBSERVE → MEASURE → EXPLAIN → HYPOTHESIZE → EXPERIMENT.

Does NOT promote to production. Promotion requires PromotionGate + authority.
"""
from __future__ import annotations

from typing import Any, Optional

from src.python.learning.attribution import attribute_episode
from src.python.learning.contracts import SignalEpisode
from src.python.learning.counterfactual import analyze_counterfactuals
from src.python.learning.drift import drift_from_episodes
from src.python.learning.experiment import (
    ExperimentLedger,
    build_experiment_from_hypothesis,
    evaluate_experiment_to_candidacy,
)
from src.python.learning.failure_memory import FailureMemory
from src.python.learning.hypothesis import generate_hypotheses_from_failures, propose_experiments_for_hypothesis
from src.python.learning.introspection import diagnose
from src.python.learning.knowledge import KnowledgeBase
from src.python.learning.meta_learner import MetaLearner


class LearningLoop:
    """Closed-loop learning over paper outcomes. Champion/challenger only via PromotionGate."""

    def __init__(
        self,
        *,
        failure_memory: Optional[FailureMemory] = None,
        knowledge: Optional[KnowledgeBase] = None,
        experiments: Optional[ExperimentLedger] = None,
        meta: Optional[MetaLearner] = None,
    ):
        self.failures = failure_memory or FailureMemory()
        self.knowledge = knowledge or KnowledgeBase()
        self.experiments = experiments or ExperimentLedger()
        self.meta = meta or MetaLearner()
        self.episodes: list[SignalEpisode] = []

    def observe_episode(self, ep: SignalEpisode) -> dict[str, Any]:
        self.episodes.append(ep)
        self.meta.observe(ep)
        attr = attribute_episode(ep)
        cf = analyze_counterfactuals(ep)
        fail = None
        if float(ep.r_multiple or 0) < -0.1 or ep.outcome == "LOSS":
            fail = self.failures.observe(ep, failure_id=f"FAIL-{ep.episode_id}")
        return {
            "episode_id": ep.episode_id,
            "attribution": attr.to_dict(),
            "counterfactual": cf.to_dict(),
            "failure": fail.to_dict() if fail else None,
        }

    def run_learning_cycle(
        self,
        *,
        historical_episodes: Optional[list[SignalEpisode]] = None,
        experiment_evidence: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        observed = self.failures.list_observed()
        hyps = generate_hypotheses_from_failures(observed, min_similar=1)
        for h in hyps:
            self.knowledge.upsert_hypothesis(h)

        exp_results = []
        registered = []
        for i, h in enumerate(hyps[:3]):
            sketches = propose_experiments_for_hypothesis(h)
            sk = sketches[0]
            exp_id = f"EXP-{h.hypothesis_id}-{i+1:02d}"
            if exp_id in self.experiments.ids():
                continue
            spec = build_experiment_from_hypothesis(
                h,
                experiment_id=exp_id,
                name=sk["name"],
                challenger_strategy_id=h.strategies[0] if h.strategies else "challenger",
                challenger_version=f"learn-{h.hypothesis_id}",
                parameters={"sketch": sk},
            )
            self.experiments.register(spec)
            registered.append(spec.to_dict())
            if experiment_evidence:
                result = evaluate_experiment_to_candidacy(spec, experiment_evidence)
                exp_results.append(result)
                assert result.get("approved") is False

        hist = historical_episodes or self.episodes[:-20]
        recent = self.episodes[-20:] if self.episodes else []
        alerts = drift_from_episodes(hist, recent) if (hist or recent) else []
        health = diagnose(
            episodes=self.episodes,
            drift_alerts=alerts,
            n_failures_observed=len(observed),
        )

        return {
            "hypotheses": [h.to_dict() for h in hyps],
            "experiments_registered": registered,
            "experiment_candidacy": exp_results,
            "drift": [a.to_dict() for a in alerts],
            "health": health.to_dict(),
            "principle": "hypothesis_ok_production_requires_promotion_gate",
        }
