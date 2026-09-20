"""Research → Learning feedback loop (advisory only).

Records experiment outcomes into KnowledgeBase so future hypothesis generation
can detect already-tried configurations. Never touches Champion / registry.
"""
from __future__ import annotations

from typing import Any, Optional

from src.python.learning.contracts import Hypothesis, LearningStatus
from src.python.learning.knowledge import KnowledgeBase
from src.python.research.experiment_result import ExperimentResult


def feedback_experiment_to_knowledge(
    result: ExperimentResult,
    *,
    knowledge: Optional[KnowledgeBase] = None,
) -> dict[str, Any]:
    kb = knowledge or KnowledgeBase()
    oos = (result.metrics or {}).get("oos") or {}
    statement = (
        f"exp:{result.experiment_id} status={result.status} "
        f"oos_n={oos.get('n_trades')} exp={oos.get('expectancy')} "
        f"fp={result.configuration_fingerprint[:16]}"
    )
    hid = f"FB-{result.experiment_id}"
    status = LearningStatus.HYPOTHESIS.value
    try:
        if result.status in ("ROBUST", "COMPLETED"):
            status = LearningStatus.VALIDATED.value
    except Exception:
        status = LearningStatus.HYPOTHESIS.value
    h = Hypothesis(
        hypothesis_id=hid,
        statement=statement[:240],
        strategies=[(result.challenger_version or "challenger").split("@")[0]],
        regimes=[],
        counter_hypothesis="",
        status=status,
        meta={
            "result_hash": result.result_hash,
            "configuration_fingerprint": result.configuration_fingerprint,
            "experiment_status": result.status,
            "advisory_only": True,
        },
    )
    kb.upsert_hypothesis(h)
    if result.status in ("FAILED", "INVALID", "FRAGILE", "INSUFFICIENT_EVIDENCE"):
        kb.mark_validated(hid, walk_forward=True, oos=False)
    elif result.status in ("ROBUST", "COMPLETED"):
        kb.mark_validated(hid, walk_forward=True, oos=True)
    return {
        "ok": True,
        "hypothesis_id": hid,
        "status": result.status,
        "production_mutation": False,
        "note": "advisory_feedback_only",
    }
