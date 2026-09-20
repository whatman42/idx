"""Adaptive ML Governor — utility + safety + budget (deterministic).

Safety has absolute priority: DQ/stale/corruption → HALT/SKIP, never model selection.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

from src.python.ml.families import FAMILY_SPECS, ModelFamily, TRAINABLE_FAMILIES
from src.python.governor.utility import score_model_utility, UtilityReport


@dataclass
class ResourceProfile:
    cpu_count: int = 2
    ram_gb: float = 4.0
    gpu_name: str = ""
    vram_gb: float = 0.0
    training_budget_sec: float = 1200.0

    @classmethod
    def detect(cls) -> "ResourceProfile":
        import os
        return cls(cpu_count=os.cpu_count() or 2)


@dataclass
class SafetyContext:
    dq_ok: bool = True
    freshness_ok: bool = True
    data_available: bool = True
    nan_safe: bool = True
    ohlc_valid: bool = True
    paper_ok: bool = True
    risk_ok: bool = True
    reason: str = ""

    def blocked(self) -> bool:
        return not all([
            self.dq_ok, self.freshness_ok, self.data_available,
            self.nan_safe, self.ohlc_valid, self.paper_ok, self.risk_ok,
        ])

    def block_reason(self) -> str:
        if self.reason:
            return self.reason
        flags = [k for k in ("dq_ok", "freshness_ok", "data_available", "nan_safe", "ohlc_valid", "paper_ok", "risk_ok") if not getattr(self, k)]
        return "safety_block:" + ",".join(flags) if flags else "ok"


@dataclass
class MarketContext:
    regime_trend: float = 0.0
    regime_vol: float = 1.0
    drift_score: float = 0.0
    feature_tier_available: int = 1


@dataclass
class MLGovernor:
    """Deterministic selection: safety → filters → utility rank → budget cut."""

    resources: ResourceProfile = field(default_factory=ResourceProfile.detect)
    utility_memory: dict[str, dict[str, Any]] = field(default_factory=dict)

    def remember_utility(self, model_id: str, report: UtilityReport | dict[str, Any]) -> None:
        d = report.to_dict() if isinstance(report, UtilityReport) else dict(report)
        self.utility_memory[model_id] = d

    def training_plan(self, remaining_sec: float) -> dict[str, Any]:
        sel = self.select_models(remaining_sec=remaining_sec, safety=SafetyContext(), market=MarketContext(), purpose="train")
        return {
            "allow_train": sel["allow"],
            "workload": sel["workload"],
            "families": sel["families"],
            "estimated_train_sec": sel["estimated_cost_sec"],
            "remaining_sec": remaining_sec,
            "policy": "utility_safety_budget_one_per_family",
            "families_available": [f.value for f in TRAINABLE_FAMILIES],
            "selection": sel,
        }

    def feature_plan(self, remaining_sec: float, *, dq_ok: bool = True) -> dict[str, Any]:
        remaining = float(remaining_sec)
        if not dq_ok:
            return {"allow_features": False, "max_tier": -1, "reason": "dq_blocked", "remaining_sec": remaining}
        if remaining < 20:
            return {"allow_features": False, "max_tier": -1, "reason": "budget_too_low", "remaining_sec": remaining}
        if remaining < 90:
            tier = 0
        elif remaining < 300:
            tier = 1
        else:
            tier = 2
        return {
            "allow_features": True,
            "max_tier": tier,
            "tier_name": {0: "TIER0_CORE", 1: "TIER1_STANDARD", 2: "TIER2_ADVANCED"}[tier],
            "remaining_sec": remaining,
            "policy": "adaptive_feature_tier",
            "note": "High hardware does not force max tier",
        }

    def select_models(
        self,
        *,
        remaining_sec: float,
        safety: Optional[SafetyContext] = None,
        market: Optional[MarketContext] = None,
        purpose: str = "shadow",
        available_families: Optional[Sequence[ModelFamily | str]] = None,
        model_metrics: Optional[dict[str, dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        safety = safety or SafetyContext()
        market = market or MarketContext()
        remaining = float(remaining_sec)
        model_metrics = model_metrics or {}

        if safety.blocked():
            return {
                "allow": False, "workload": "SKIP", "families": [], "model_ids": [],
                "estimated_cost_sec": 0.0, "reason": safety.block_reason(),
                "safety_precedence": True, "utilities": {},
            }
        if remaining < 30:
            return {
                "allow": False, "workload": "SKIP", "families": [], "model_ids": [],
                "estimated_cost_sec": 0.0, "reason": "budget_below_30s",
                "safety_precedence": True, "utilities": {},
            }

        if available_families is None:
            candidates = list(TRAINABLE_FAMILIES)
        else:
            candidates = [ModelFamily(f) if isinstance(f, str) else f for f in available_families]

        prefer_simple = market.drift_score >= 0.7 or market.regime_vol >= 2.0
        if prefer_simple:
            candidates = sorted(candidates, key=lambda f: (0 if f == ModelFamily.LOGREG_LINEAR else 1, FAMILY_SPECS[f].typical_train_sec, f.value))
        else:
            candidates = sorted(candidates, key=lambda f: (FAMILY_SPECS[f].typical_train_sec, f.value))

        utilities: dict[str, dict[str, Any]] = {}
        ranked: list[tuple[float, str, ModelFamily]] = []
        for fam in candidates:
            spec = FAMILY_SPECS[fam]
            mid = spec.model_id
            mem = self.utility_memory.get(mid) or model_metrics.get(mid) or {}
            metrics = mem if isinstance(mem, dict) else {}
            ur = score_model_utility(
                model_id=mid, family=fam.value,
                metrics=metrics,
                train_sec=float(metrics["train_sec"]) if metrics.get("train_sec") is not None else FAMILY_SPECS[fam].typical_train_sec,
                budget_sec=remaining,
            )
            if "score" in mem and mem.get("status"):
                try:
                    ur = UtilityReport(mid, fam.value, str(mem.get("status")), float(mem.get("score", ur.score)), ur.components, ur.reasons)
                except (TypeError, ValueError, KeyError) as e:
                    ur = UtilityReport(
                        mid, fam.value, ur.status,
                        float(ur.score), ur.components,
                        list(ur.reasons) + [f"memory_override_skipped:{type(e).__name__}"],
                    )
            utilities[mid] = ur.to_dict()
            ranked.append((ur.score, mid, fam))

        ranked.sort(key=lambda t: (-t[0], FAMILY_SPECS[t[2]].typical_train_sec, t[1]))

        selected: list[ModelFamily] = []
        cost = 0.0
        seen_family: set[ModelFamily] = set()
        for score, mid, fam in ranked:
            if fam in seen_family:
                continue
            need = FAMILY_SPECS[fam].typical_train_sec
            if purpose == "shadow":
                need = max(5.0, need * 0.25)
            if cost + need > remaining - 5:
                continue
            if prefer_simple and fam == ModelFamily.LGBM_BOOST and score <= 0.0 and selected:
                continue
            selected.append(fam)
            seen_family.add(fam)
            cost += need

        if not selected and remaining >= 30:
            selected = [ModelFamily.LOGREG_LINEAR]
            cost = FAMILY_SPECS[ModelFamily.LOGREG_LINEAR].typical_train_sec * (0.25 if purpose == "shadow" else 1.0)

        model_ids = [FAMILY_SPECS[f].model_id for f in selected]
        workload = "SKIP" if not selected else ("MULTI_FAMILY_LIGHTWEIGHT" if len(selected) > 1 else selected[0].value)
        return {
            "allow": bool(selected),
            "workload": workload,
            "families": [f.value for f in selected],
            "model_ids": model_ids,
            "estimated_cost_sec": cost,
            "reason": "selected",
            "safety_precedence": True,
            "utilities": utilities,
            "purpose": purpose,
            "prefer_simple": prefer_simple,
            "policy": "utility_safety_budget_one_per_family",
        }
