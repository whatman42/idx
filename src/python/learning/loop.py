"""Learning Loop orchestrator — OBSERVE → MEASURE → EXPLAIN → HYPOTHESIZE → EXPERIMENT.

Does NOT promote to production. Promotion requires PromotionGate + authority.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from src.python.learning.attribution import attribute_episode
from src.python.learning.contracts import SignalEpisode
from src.python.learning.counterfactual import analyze_counterfactuals
from src.python.learning.drift import drift_from_episodes
from src.python.learning.episodes import EpisodeStore, ingest_closed_trades_from_portfolio
from src.python.learning.experiment import (
    ExperimentLedger,
    build_experiment_from_hypothesis,
    evaluate_experiment_to_candidacy,
)
from src.python.learning.failure_memory import FailureMemory
from src.python.learning.hypothesis import generate_hypotheses_from_failures, propose_experiments_for_hypothesis
from src.python.learning.integrity import gate_learning_on_integrity, reconcile_episode_pnl
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
        episode_store: Optional[EpisodeStore] = None,
        state_dir: Optional[Path] = None,
    ):
        base = Path(state_dir) if state_dir else None
        self.failures = failure_memory or FailureMemory(
            path=(base / "failures.json") if base else None
        )
        self.knowledge = knowledge or KnowledgeBase(
            path=(base / "knowledge.json") if base else None
        )
        self.experiments = experiments or ExperimentLedger(
            path=(base / "experiments.json") if base else None
        )
        self.meta = meta or MetaLearner()
        self.episode_store = episode_store or EpisodeStore(
            path=(base / "episodes.json") if base else None
        )
        self.episodes: list[SignalEpisode] = list(self.episode_store.list_all())

    def observe_episode(self, ep: SignalEpisode) -> dict[str, Any]:
        # Synthetic/test episodes may omit identity keys; derive stable ones.
        if not ep.idempotency_key:
            from src.python.learning.episodes import make_episode_id, make_idempotency_key
            ep.idempotency_key = make_idempotency_key(
                signal_id=ep.signal_id or ep.episode_id,
                symbol=ep.symbol,
                entry_trade_id=ep.entry_trade_id or "synth",
                exit_trade_id=ep.fill_id or ep.episode_id,
            )
            if not ep.episode_id:
                ep.episode_id = make_episode_id(ep.idempotency_key)
            if not ep.fill_id:
                ep.fill_id = ep.episode_id
            if ep.lifecycle == "OPEN" and ep.outcome not in ("OPEN", "SKIPPED"):
                ep.lifecycle = "COMPLETED"
        stored, _ = self.episode_store.upsert(ep)
        if stored.episode_id not in {e.episode_id for e in self.episodes}:
            self.episodes.append(stored)
        self.meta.observe(stored)
        attr = attribute_episode(stored)
        cf = analyze_counterfactuals(stored)
        fail = None
        if float(stored.r_multiple or 0) < -0.1 or stored.outcome == "LOSS":
            fail = self.failures.observe(stored, failure_id=f"FAIL-{stored.episode_id}")
        return {
            "episode_id": stored.episode_id,
            "idempotency_key": stored.idempotency_key,
            "lifecycle": stored.lifecycle,
            "attribution": attr.to_dict(),
            "counterfactual": cf.to_dict(),
            "failure": fail.to_dict() if fail else None,
        }

    def ingest_from_paper_trades(
        self,
        trades: list[dict[str, Any]],
        *,
        strategy_id: str = "rule_sma20",
        session_id: str = "",
        ledger_realized_pnl: Optional[float] = None,
    ) -> dict[str, Any]:
        """Paper fills → episodes → integrity gate. Research only. Never mutates ledger."""
        summary = ingest_closed_trades_from_portfolio(
            trades,
            store=self.episode_store,
            strategy_id=strategy_id,
            session_id=session_id,
        )
        self.episodes = list(self.episode_store.list_all())
        completed = self.episode_store.list_completed()
        closed_pnls = [
            float(t.get("pnl") or 0)
            for t in trades
            if str(t.get("action", "")).upper() in ("SELL", "EXIT")
        ]
        integrity = reconcile_episode_pnl(
            completed,
            ledger_realized_pnl=ledger_realized_pnl,
            closed_trade_pnls=closed_pnls if closed_pnls else None,
        )
        gate = gate_learning_on_integrity(integrity)
        observed = []
        if gate["learning_update"] == "ALLOW":
            for ep in completed:
                if ep.lifecycle == "COMPLETED":
                    observed.append(self.observe_episode(ep))
        return {
            "ingest": summary,
            "integrity": integrity.to_dict(),
            "gate": gate,
            "observed": observed,
            "principle": "research_only_no_execution",
        }

    def run_learning_cycle(
        self,
        *,
        historical_episodes: Optional[list[SignalEpisode]] = None,
        experiment_evidence: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        integrity = reconcile_episode_pnl(self.episodes)
        gate = gate_learning_on_integrity(integrity)
        if gate["learning_update"] == "BLOCKED":
            return {
                "hypotheses": [],
                "experiments_registered": [],
                "experiment_candidacy": [],
                "drift": [],
                "health": diagnose(episodes=self.episodes).to_dict(),
                "integrity": integrity.to_dict(),
                "gate": gate,
                "principle": "hypothesis_ok_production_requires_promotion_gate",
                "blocked_reason": "LEARNING_DATA_INTEGRITY_FAIL",
            }

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
            "integrity": integrity.to_dict(),
            "gate": gate,
            "principle": "hypothesis_ok_production_requires_promotion_gate",
        }
