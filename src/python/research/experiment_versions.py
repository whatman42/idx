"""Versioned research experiments — registry only, never production.

Each entry is a candidate hypothesis that MUST go through:
  FeatureSnapshot → Scorer (shadow) → WFA → EvidencePackage → Gate → Manual Review

None of these are production-eligible until explicit human lifecycle decision.
"""
from __future__ import annotations

from typing import Any


EXPERIMENT_REGISTRY: dict[str, dict[str, Any]] = {
    "crypto_mom_shadow_v1": {
        "plane": "CRYPTO_RESEARCH",
        "status": "REJECTED_KEEP_SHADOW",
        "hypothesis": "ret_5>0 AND sma_dist_20>0 adds alpha vs SMA20",
        "result_note": "Full sample showed no incremental expectancy vs SMA20 reference",
        "production_eligible": False,
    },
    "crypto_sma20_crossover_v1": {
        "plane": "CRYPTO_RESEARCH",
        "status": "PROPOSED",
        "hypothesis": "Close crosses above SMA20 (event) reduces level-condition churn vs close>SMA20",
        "params": {"lookback": 20, "signal": "cross_up", "hold_bars": 5},
        "production_eligible": False,
        "required_evidence": [
            "WFA fold consistency on VALID folds only",
            "decay_ratio_expectancy classification",
            "per-symbol VALID distribution",
            "net cost after simulation fees",
        ],
    },
    "crypto_sma20_cooldown_v1": {
        "plane": "CRYPTO_RESEARCH",
        "status": "PROPOSED",
        "hypothesis": "Re-entry cooldown after exit cuts turnover without destroying expectancy",
        "params": {"lookback": 20, "cooldown_bars": 3, "hold_bars": 5},
        "production_eligible": False,
        "required_evidence": [
            "Trade count reduction vs baseline",
            "Expectancy and max DD vs SMA20 reference",
            "decay_ratio and fold consistency",
        ],
    },
    "idx_cost_sensitivity_v1": {
        "plane": "IDX_RESEARCH",
        "status": "PROPOSED",
        "hypothesis": "IDXBrokerCostModel sensitivity does not flip SMA20 paper sign vs SimulationCostModel",
        "production_eligible": False,
        "required_evidence": [
            "Side-by-side expectancy_after_cost",
            "Explicit note: paper path stays Simulation until calibrated",
        ],
    },
}


def list_experiments(*, plane: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for eid, meta in EXPERIMENT_REGISTRY.items():
        if plane and str(meta.get("plane") or "") != plane:
            continue
        rows.append({"experiment_id": eid, **meta})
    return rows


def get_experiment(experiment_id: str) -> dict[str, Any] | None:
    meta = EXPERIMENT_REGISTRY.get(experiment_id)
    if not meta:
        return None
    return {"experiment_id": experiment_id, **meta}


def assert_not_production(experiment_id: str) -> None:
    meta = EXPERIMENT_REGISTRY.get(experiment_id)
    if meta and meta.get("production_eligible"):
        raise RuntimeError(f"{experiment_id} must not be production_eligible without lifecycle process")
    if meta is None:
        return
    if meta.get("production_eligible") is not False:
        raise RuntimeError(f"{experiment_id}: production_eligible must be explicitly False")
