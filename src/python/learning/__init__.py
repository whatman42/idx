"""Adaptive Decision & Learning System — closed loop above Strategy Engine.

Layers:
  PERCEPTION → REASONING → DECISION → EXPERIENCE → LEARNING → EVOLUTION

Evolution always goes through EvidencePackage + PromotionGate.
LLM/Gemini is reasoning-only; never SSOT for price/PnL/features/signals.
"""
from src.python.learning.attribution import attribute_batch, attribute_episode
from src.python.learning.contracts import (
    AttributionReport,
    CounterfactualReport,
    ExperimentSpec,
    FailureRecord,
    HealthReport,
    Hypothesis,
    LearningStatus,
    MetaDecision,
    SignalEpisode,
)
from src.python.learning.counterfactual import analyze_counterfactuals
from src.python.learning.drift import drift_from_episodes, performance_drift
from src.python.learning.experiment import ExperimentLedger, evaluate_experiment_to_candidacy
from src.python.learning.failure_memory import FailureMemory
from src.python.learning.hypothesis import generate_hypotheses_from_failures
from src.python.learning.introspection import diagnose
from src.python.learning.knowledge import KnowledgeBase
from src.python.learning.loop import LearningLoop
from src.python.learning.meta_learner import MetaLearner

__all__ = [
    "SignalEpisode",
    "AttributionReport",
    "FailureRecord",
    "Hypothesis",
    "CounterfactualReport",
    "ExperimentSpec",
    "MetaDecision",
    "HealthReport",
    "LearningStatus",
    "attribute_episode",
    "attribute_batch",
    "analyze_counterfactuals",
    "FailureMemory",
    "generate_hypotheses_from_failures",
    "ExperimentLedger",
    "evaluate_experiment_to_candidacy",
    "MetaLearner",
    "drift_from_episodes",
    "performance_drift",
    "diagnose",
    "KnowledgeBase",
    "LearningLoop",
]
