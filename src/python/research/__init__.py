"""Research plane — adaptive / experimental; never mutates Champion automatically.

GitHub Actions = control plane (cheap)
Colab          = research compute (expensive)
LLM            = reasoning only
PromotionGate  = mandatory evidence barrier
"""
from src.python.research.adoption import ADOPTION_MATRIX, AdoptionDecision, matrix_as_dicts
from src.python.research.colab_jobs import ColabResearchJob, ResearchJobKind, make_job, validate_job
from src.python.research.cycle import ResearchCycle
from src.python.research.factory import FailureCluster, ResearchBatch, ResearchFactory, cluster_failures
from src.python.research.regime_matrix import RegimeCell, RegimeMatrix

__all__ = [
    "ADOPTION_MATRIX",
    "AdoptionDecision",
    "matrix_as_dicts",
    "ColabResearchJob",
    "ResearchJobKind",
    "make_job",
    "validate_job",
    "ResearchCycle",
    "FailureCluster",
    "ResearchBatch",
    "ResearchFactory",
    "cluster_failures",
    "RegimeCell",
    "RegimeMatrix",
]
