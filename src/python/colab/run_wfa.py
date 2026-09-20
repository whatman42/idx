"""Colab-facing WFA launcher — thin wrapper over research.wfa_executor.

Never mutates Champion. Never auto-promotes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.python.research.colab_jobs import ColabResearchJob
from src.python.research.evidence_bridge import (
    evaluate_research_candidacy,
    experiment_result_to_evidence,
    experiment_result_to_evidence_package,
)
from src.python.research.experiment_result import ExperimentResultStore
from src.python.research.feedback import feedback_experiment_to_knowledge
from src.python.research.wfa_executor import WFAExecutor


def run_wfa_job(
    job: ColabResearchJob | dict[str, Any],
    bars: pd.DataFrame,
    *,
    artifact_dir: Optional[str | Path] = None,
    champion_snapshot: Optional[dict[str, Any]] = None,
    run_gate_candidacy: bool = True,
    feedback_to_learning: bool = True,
) -> dict[str, Any]:
    if isinstance(job, dict):
        job = ColabResearchJob(**{k: job[k] for k in ColabResearchJob.__dataclass_fields__ if k in job})
    store = ExperimentResultStore(Path(artifact_dir) if artifact_dir else None)
    exe = WFAExecutor(store=store)
    result = exe.execute(job, bars, champion_snapshot=champion_snapshot, allow_champion_write=False)
    pkg = experiment_result_to_evidence_package(result)
    evidence = experiment_result_to_evidence(result)
    candidacy = None
    if run_gate_candidacy:
        candidacy = evaluate_research_candidacy(result)
        assert candidacy.get("approved") is False
    feedback = None
    if feedback_to_learning:
        feedback = feedback_experiment_to_knowledge(result)
    return {
        "result": result.to_dict(),
        "evidence_package": pkg.to_dict() if hasattr(pkg, "to_dict") else pkg.to_promotion_evidence(),
        "evidence": evidence,
        "candidacy": candidacy,
        "feedback": feedback,
        "production_mutation": False,
        "auto_promote": False,
        "champion_write": False,
    }
