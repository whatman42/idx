"""Colab-facing WFA launcher — thin wrapper over research.wfa_executor.

Never mutates Champion. Never auto-promotes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.python.research.colab_jobs import ColabResearchJob
from src.python.research.experiment_result import ExperimentResultStore
from src.python.research.wfa_executor import WFAExecutor, experiment_result_to_evidence


def run_wfa_job(
    job: ColabResearchJob | dict[str, Any],
    bars: pd.DataFrame,
    *,
    artifact_dir: Optional[str | Path] = None,
    champion_snapshot: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    if isinstance(job, dict):
        job = ColabResearchJob(**{k: job[k] for k in ColabResearchJob.__dataclass_fields__ if k in job})
    store = ExperimentResultStore(Path(artifact_dir) if artifact_dir else None)
    exe = WFAExecutor(store=store)
    result = exe.execute(job, bars, champion_snapshot=champion_snapshot, allow_champion_write=False)
    evidence = experiment_result_to_evidence(result)
    return {
        "result": result.to_dict(),
        "evidence": evidence,
        "production_mutation": False,
        "auto_promote": False,
        "champion_write": False,
    }
