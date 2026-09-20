"""External dependency failure model — research plane only.

EXTERNAL FAILURE ≠ DATA SUCCESS
External services never become authority over Ledger / Champion / Promotion.
"""
from src.python.external.states import (
    DependencyKind,
    DependencyReport,
    DependencyStatus,
    ResearchJobDependencyState,
    classify_exception,
)
from src.python.external.gate import (
    evaluate_research_job_readiness,
    fail_closed_promotion_on_deps,
)

__all__ = [
    "DependencyKind",
    "DependencyReport",
    "DependencyStatus",
    "ResearchJobDependencyState",
    "classify_exception",
    "evaluate_research_job_readiness",
    "fail_closed_promotion_on_deps",
]
