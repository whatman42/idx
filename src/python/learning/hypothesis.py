"""Hypothesis Engine — observation → pattern → hypothesis → counter-hypothesis."""
from __future__ import annotations

from collections import Counter
from typing import Any

from src.python.learning.contracts import FailureRecord, Hypothesis, LearningStatus


def generate_hypotheses_from_failures(
    failures: list[FailureRecord],
    *,
    prefix: str = "HYP",
    min_similar: int = 3,
) -> list[Hypothesis]:
    """Deterministic hypothesis generation from failure memory patterns."""
    out: list[Hypothesis] = []
    key_counts: Counter[tuple[str, str, str]] = Counter()
    for f in failures:
        key_counts[(f.strategy_id, f.regime, f.root_cause)] += 1

    idx = 1
    for (strategy_id, regime, root), n in key_counts.most_common():
        if n < min_similar and n < 1:
            continue
        if not failures:
            break
        hid = f"{prefix}-{idx:05d}"
        idx += 1
        statement = (
            f"{strategy_id} degrades in regime={regime} due to {root}; "
            f"observed_n={n}"
        )
        counter = (
            f"Not {strategy_id}: regime classifier lag or sizing, not signal logic"
        )
        out.append(Hypothesis(
            hypothesis_id=hid,
            statement=statement,
            regimes=[regime],
            strategies=[strategy_id],
            counter_hypothesis=counter,
            status=LearningStatus.HYPOTHESIS.value,
            evidence_count=n,
            meta={"root_cause": root},
        ))
        if len(out) >= 5:
            break
    return out


def propose_experiments_for_hypothesis(h: Hypothesis) -> list[dict[str, Any]]:
    """Three experiment sketches: filter, regime, sizing — not auto-applied."""
    strat = h.strategies[0] if h.strategies else "unknown"
    return [
        {
            "name": f"{strat}_persistence_filter",
            "kind": "strategy_filter",
            "hypothesis_id": h.hypothesis_id,
            "description": "Add persistence filter to reduce false breakouts",
        },
        {
            "name": f"{strat}_regime_tighten",
            "kind": "regime_filter",
            "hypothesis_id": h.hypothesis_id,
            "description": "Tighten regime gate for SIDEWAYS/HIGH_VOL",
        },
        {
            "name": f"{strat}_size_reduce",
            "kind": "sizing",
            "hypothesis_id": h.hypothesis_id,
            "description": "Reduce size only; keep signal logic unchanged",
        },
    ]
