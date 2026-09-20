"""Research plane — adaptive / experimental; never mutates Champion automatically.

GitHub Actions = control plane (cheap)
Colab          = research compute (expensive)
LLM            = reasoning only
PromotionGate  = mandatory evidence barrier
"""
from src.python.research.adoption import ADOPTION_MATRIX, AdoptionDecision, matrix_as_dicts
from src.python.research.budget import ResearchBudget
from src.python.research.colab_jobs import ColabResearchJob, ResearchJobKind, make_job, validate_job
from src.python.research.cycle import ResearchCycle
from src.python.research.evidence_bridge import (
    evaluate_research_candidacy,
    experiment_result_to_evidence,
    experiment_result_to_evidence_package,
)
from src.python.research.experiment_result import ExperimentResult, ExperimentResultStore
from src.python.research.factory import FailureCluster, ResearchBatch, ResearchFactory, cluster_failures
from src.python.research.feedback import feedback_experiment_to_knowledge
from src.python.research.queue import ResearchQueue
from src.python.research.regime_matrix import RegimeCell, RegimeMatrix
from src.python.research.reproducibility import ReproReport, verify_reproducibility
from src.python.research.wfa_executor import WFAExecutor, validate_pit_features

__all__ = [
    "ADOPTION_MATRIX",
    "AdoptionDecision",
    "matrix_as_dicts",
    "ResearchBudget",
    "ColabResearchJob",
    "ResearchJobKind",
    "make_job",
    "validate_job",
    "ResearchCycle",
    "evaluate_research_candidacy",
    "experiment_result_to_evidence",
    "experiment_result_to_evidence_package",
    "ExperimentResult",
    "ExperimentResultStore",
    "FailureCluster",
    "ResearchBatch",
    "ResearchFactory",
    "cluster_failures",
    "feedback_experiment_to_knowledge",
    "ResearchQueue",
    "RegimeCell",
    "RegimeMatrix",
    "ReproReport",
    "verify_reproducibility",
    "WFAExecutor",
    "validate_pit_features",
]
