"""Autonomous Research Factory — RD-Agent-inspired, IDX-constrained.

Flow (research plane only):
  episodes → failure clusters → patterns → hypotheses → experiment batch
  → (Colab/WFA later) → EvidencePackage → PromotionGate → Authority

Never mutates Champion. Never submits orders. Never bypasses PromotionGate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from src.python.learning.contracts import FailureRecord, Hypothesis, LearningStatus, SignalEpisode
from src.python.learning.experiment import (
    ExperimentLedger,
    build_experiment_from_hypothesis,
)
from src.python.learning.hypothesis import generate_hypotheses_from_failures, propose_experiments_for_hypothesis
from src.python.learning.knowledge import KnowledgeBase
from src.python.research.regime_matrix import RegimeMatrix


@dataclass
class FailureCluster:
    strategy_id: str
    regime: str
    root_cause: str
    count: int
    avg_r: float
    pattern: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ResearchBatch:
    """Generated research work — candidates for Colab, not production."""
    clusters: list[FailureCluster] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    experiment_ids: list[str] = field(default_factory=list)
    regime_insights: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "clusters": [c.to_dict() for c in self.clusters],
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "experiment_ids": list(self.experiment_ids),
            "regime_insights": list(self.regime_insights),
            "notes": list(self.notes),
            "production_mutation": False,
            "promotion_required": True,
        }


def cluster_failures(failures: list[FailureRecord], *, min_count: int = 2) -> list[FailureCluster]:
    buckets: dict[tuple[str, str, str], list[FailureRecord]] = defaultdict(list)
    for f in failures:
        key = (f.strategy_id, (f.regime or "unknown").lower(), f.root_cause or "UNKNOWN")
        buckets[key].append(f)
    out: list[FailureCluster] = []
    for (sid, regime, root), rows in sorted(buckets.items(), key=lambda x: -len(x[1])):
        if len(rows) < min_count:
            continue
        avg_r = sum(float(r.r_multiple or 0) for r in rows) / len(rows)
        patterns = Counter((r.pattern or root) for r in rows)
        pattern = patterns.most_common(1)[0][0] if patterns else root
        out.append(FailureCluster(
            strategy_id=sid, regime=regime, root_cause=root,
            count=len(rows), avg_r=avg_r, pattern=str(pattern),
        ))
    return out


class ResearchFactory:
    """Builds research batches from failure memory + regime matrix."""

    def __init__(
        self,
        *,
        knowledge: Optional[KnowledgeBase] = None,
        ledger: Optional[ExperimentLedger] = None,
        regime_matrix: Optional[RegimeMatrix] = None,
    ):
        self.knowledge = knowledge or KnowledgeBase()
        self.ledger = ledger or ExperimentLedger()
        self.regime_matrix = regime_matrix or RegimeMatrix()

    def build_batch(
        self,
        *,
        failures: list[FailureRecord],
        episodes: Optional[list[SignalEpisode]] = None,
        max_hypotheses: int = 5,
        max_experiments: int = 5,
    ) -> ResearchBatch:
        batch = ResearchBatch()
        if episodes:
            self.regime_matrix.observe_many(episodes)
        batch.clusters = cluster_failures(failures, min_count=1)
        hyps = generate_hypotheses_from_failures(failures, min_similar=1)[:max_hypotheses]
        filtered: list[Hypothesis] = []
        for h in hyps:
            prior = self.knowledge.already_tried(h.statement[:40])
            if prior:
                batch.notes.append(f"skip_duplicate:{h.hypothesis_id}")
                continue
            self.knowledge.upsert_hypothesis(h)
            filtered.append(h)
        batch.hypotheses = filtered

        exp_n = 0
        for h in filtered:
            if exp_n >= max_experiments:
                break
            sketches = propose_experiments_for_hypothesis(h)
            for i, sk in enumerate(sketches[:1]):
                exp_id = f"EXP-{h.hypothesis_id}-{i+1:02d}"
                if exp_id in self.ledger.ids():
                    batch.notes.append(f"exp_exists:{exp_id}")
                    continue
                spec = build_experiment_from_hypothesis(
                    h,
                    experiment_id=exp_id,
                    name=sk["name"],
                    challenger_strategy_id=h.strategies[0] if h.strategies else "challenger",
                    challenger_version=f"research-{h.hypothesis_id}",
                    parameters={"sketch": sk, "source": "research_factory"},
                )
                self.ledger.register(spec)
                batch.experiment_ids.append(exp_id)
                exp_n += 1

        for cell in self.regime_matrix.weak_pairs(max_expectancy=0.0, min_n=3):
            batch.regime_insights.append({
                "strategy_id": cell.strategy_id,
                "regime": cell.regime,
                "expectancy_r": cell.expectancy_r,
                "n": cell.n,
                "recommendation": "research_penalty_or_filter",
            })
        batch.notes.append("no_production_mutation")
        batch.notes.append("promotion_requires_evidence_and_authority")
        return batch
