"""Promotion Gate — control-plane, not a single performance score.

Principles (IDX):
  Performance creates evidence;
  Evidence creates candidacy;
  Authority creates promotion;
  Production-control enforces promotion.

Three gate layers:
  1. HARD GATE     — never skippable; FAIL → REJECT
  2. EVIDENCE GATE — multi-dimension AND; FAIL → stay RESEARCH / EVALUATED
  3. AUTHORITY GATE — explicit human/ops approval; model cannot self-promote

Statuses:
  RESEARCH → EVALUATED → CANDIDATE → (authority) → PROMOTED
                                     ↘ REJECTED / RETIRED

SMA20 (rule_sma20) is baseline PROMOTED. Challengers stay RESEARCH/SHADOW
until EvidencePackage + authority clearance. Never promote on Sharpe alone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.python.strategy.contracts import StrategyLifecycle


class PromotionStage(str, Enum):
    HARD = "HARD"
    EVIDENCE = "EVIDENCE"
    AUTHORITY = "AUTHORITY"
    SIGNAL = "SIGNAL"
    BACKTEST = "BACKTEST"
    WALK_FORWARD = "WALK_FORWARD"
    OUT_OF_SAMPLE = "OUT_OF_SAMPLE"
    COST_ADJUSTED = "COST_ADJUSTED"
    STABILITY = "STABILITY"
    REGIME_ANALYSIS = "REGIME_ANALYSIS"
    BASELINE = "BASELINE"
    REPRODUCIBILITY = "REPRODUCIBILITY"
    PROMOTE = "PROMOTE"


class GateLayer(str, Enum):
    HARD = "HARD"
    EVIDENCE = "EVIDENCE"
    AUTHORITY = "AUTHORITY"


class GateOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class GateCheck:
    name: str
    layer: GateLayer
    outcome: GateOutcome
    reason: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "layer": self.layer.value,
            "outcome": self.outcome.value,
            "reason": self.reason,
            "metrics": self.metrics,
        }


@dataclass
class StageResult:
    stage: PromotionStage
    passed: bool
    reason: str
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value if isinstance(self.stage, Enum) else str(self.stage),
            "passed": self.passed,
            "reason": self.reason,
            "metrics": self.metrics,
        }


@dataclass
class PromotionDecision:
    strategy_id: str
    strategy_version: str
    evidence_id: str
    dataset_hash: str = ""
    feature_hash: str = ""
    cost_model: str = "simulation_v2"
    evaluation_date: str = ""
    lifecycle_status: str = StrategyLifecycle.RESEARCH.value
    approved: bool = False
    candidacy: bool = False
    hard_passed: bool = False
    evidence_passed: bool = False
    authority_passed: bool = False
    authority_required: bool = True
    authority_id: str = ""
    promotion_id: str = ""
    baseline_id: str = "rule_sma20@1.0"
    final_stage: str = PromotionStage.HARD.value
    reason: str = ""
    checks: list[GateCheck] = field(default_factory=list)
    stages: list[StageResult] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "evidence_id": self.evidence_id,
            "dataset_hash": self.dataset_hash,
            "feature_hash": self.feature_hash,
            "cost_model": self.cost_model,
            "evaluation_date": self.evaluation_date,
            "lifecycle_status": self.lifecycle_status,
            "approved": self.approved,
            "candidacy": self.candidacy,
            "hard_passed": self.hard_passed,
            "evidence_passed": self.evidence_passed,
            "authority_passed": self.authority_passed,
            "authority_required": self.authority_required,
            "authority_id": self.authority_id,
            "promotion_id": self.promotion_id,
            "baseline_id": self.baseline_id,
            "final_stage": self.final_stage,
            "reason": self.reason,
            "checks": [c.to_dict() for c in self.checks],
            "stages": [s.to_dict() for s in self.stages],
            "notes": list(self.notes),
        }


PromotionVerdict = PromotionDecision


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _f(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except (TypeError, ValueError):
        return default


def _i(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except (TypeError, ValueError):
        return default


class PromotionGate:
    """Multi-layer promotion evaluator. Default = not promoted.

    Does NOT write registry status. Callers apply authority + registry update.
    evaluate() returns at most CANDIDATE. PROMOTED only via apply_authority().
    """

    def __init__(
        self,
        *,
        min_trades: int = 30,
        min_oos_trades: int = 20,
        min_expectancy: float = 0.0,
        min_profit_factor: float = 1.0,
        max_drawdown: float = 0.25,
        min_wf_periods: int = 3,
        min_oos_expectancy: float = 0.0,
        max_param_sensitivity: float = 0.5,
        min_wf_pass_rate: float = 0.5,
        require_cost_model: bool = True,
        require_feature_ssot: bool = True,
        require_baseline_comparison: bool = True,
        max_baseline_dd_worsen: float = 0.05,
        min_baseline_edge: float = 0.0,
        baseline_id: str = "rule_sma20@1.0",
    ):
        self.min_trades = min_trades
        self.min_oos_trades = min_oos_trades
        self.min_expectancy = min_expectancy
        self.min_profit_factor = min_profit_factor
        self.max_drawdown = max_drawdown
        self.min_wf_periods = min_wf_periods
        self.min_oos_expectancy = min_oos_expectancy
        self.max_param_sensitivity = max_param_sensitivity
        self.min_wf_pass_rate = min_wf_pass_rate
        self.require_cost_model = require_cost_model
        self.require_feature_ssot = require_feature_ssot
        self.require_baseline_comparison = require_baseline_comparison
        self.max_baseline_dd_worsen = max_baseline_dd_worsen
        self.min_baseline_edge = min_baseline_edge
        self.baseline_id = baseline_id

    def evaluate(self, strategy_id: str, evidence: dict[str, Any]) -> PromotionDecision:
        checks: list[GateCheck] = []
        stages: list[StageResult] = []
        notes: list[str] = []

        strategy_version = str(evidence.get("strategy_version") or evidence.get("version") or "0.0.0")
        evidence_id = str(evidence.get("evidence_id") or f"EP-{strategy_id}-UNSET")
        dataset_hash = str(evidence.get("dataset_hash") or "")
        feature_hash = str(evidence.get("feature_hash") or "")
        cost_model = str(evidence.get("cost_model") or evidence.get("cost_model_id") or "unknown")
        evaluation_date = str(evidence.get("evaluation_date") or _now_iso())

        hard_ok, hard_reason = self._run_hard_gates(evidence, checks, stages)
        if not hard_ok:
            return PromotionDecision(
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                evidence_id=evidence_id,
                dataset_hash=dataset_hash,
                feature_hash=feature_hash,
                cost_model=cost_model,
                evaluation_date=evaluation_date,
                lifecycle_status=StrategyLifecycle.REJECTED.value,
                approved=False,
                candidacy=False,
                hard_passed=False,
                evidence_passed=False,
                authority_passed=False,
                final_stage=PromotionStage.HARD.value,
                reason=hard_reason,
                checks=checks,
                stages=stages,
                notes=notes,
                baseline_id=self.baseline_id,
            )

        ev_ok, ev_reason = self._run_evidence_gates(evidence, checks, stages, notes)
        if not ev_ok:
            return PromotionDecision(
                strategy_id=strategy_id,
                strategy_version=strategy_version,
                evidence_id=evidence_id,
                dataset_hash=dataset_hash,
                feature_hash=feature_hash,
                cost_model=cost_model,
                evaluation_date=evaluation_date,
                lifecycle_status=StrategyLifecycle.EVALUATED.value,
                approved=False,
                candidacy=False,
                hard_passed=True,
                evidence_passed=False,
                authority_passed=False,
                final_stage=PromotionStage.EVIDENCE.value,
                reason=ev_reason,
                checks=checks,
                stages=stages,
                notes=notes,
                baseline_id=self.baseline_id,
            )

        notes.append("evidence_cleared_awaiting_authority")
        stages.append(StageResult(
            PromotionStage.PROMOTE, False, "authority_required_not_self_promote", {},
        ))
        return PromotionDecision(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            evidence_id=evidence_id,
            dataset_hash=dataset_hash,
            feature_hash=feature_hash,
            cost_model=cost_model,
            evaluation_date=evaluation_date,
            lifecycle_status=StrategyLifecycle.CANDIDATE.value,
            approved=False,
            candidacy=True,
            hard_passed=True,
            evidence_passed=True,
            authority_passed=False,
            authority_required=True,
            final_stage=PromotionStage.AUTHORITY.value,
            reason="candidate_pending_authority",
            checks=checks,
            stages=stages,
            notes=notes,
            baseline_id=self.baseline_id,
        )

    def apply_authority(
        self,
        decision: PromotionDecision,
        *,
        authority_id: str,
        approve: bool,
        promotion_id: str = "",
        note: str = "",
    ) -> PromotionDecision:
        if not decision.hard_passed or not decision.evidence_passed or not decision.candidacy:
            decision.reason = "authority_blocked_not_candidate"
            decision.authority_passed = False
            decision.approved = False
            decision.notes.append("authority_rejected_non_candidate")
            return decision

        if not authority_id or not str(authority_id).strip():
            decision.reason = "authority_id_required"
            decision.authority_passed = False
            decision.approved = False
            decision.notes.append("missing_authority_id")
            return decision

        decision.authority_id = str(authority_id).strip()
        decision.checks.append(GateCheck(
            name="authority_explicit",
            layer=GateLayer.AUTHORITY,
            outcome=GateOutcome.PASS if approve else GateOutcome.FAIL,
            reason=note or ("approved" if approve else "rejected_by_authority"),
            metrics={"authority_id": decision.authority_id},
        ))

        if approve:
            decision.authority_passed = True
            decision.approved = True
            decision.lifecycle_status = StrategyLifecycle.PROMOTED.value
            decision.promotion_id = promotion_id or f"PROM-{decision.strategy_id}-{decision.evaluation_date[:10]}"
            decision.final_stage = PromotionStage.PROMOTE.value
            decision.reason = "promoted_by_authority"
            decision.stages.append(StageResult(
                PromotionStage.PROMOTE, True, "authority_approved",
                {"promotion_id": decision.promotion_id, "authority_id": decision.authority_id},
            ))
            if note:
                decision.notes.append(note)
            from src.python.strategy.promotion_invariants import promoted_record_missing_fields
            missing = promoted_record_missing_fields(decision)
            if missing:
                decision.approved = False
                decision.authority_passed = False
                decision.lifecycle_status = StrategyLifecycle.CANDIDATE.value
                decision.reason = f"promoted_invariant_fail:{','.join(missing)}"
                decision.notes.append(decision.reason)
                return decision
        else:
            decision.authority_passed = False
            decision.approved = False
            decision.lifecycle_status = StrategyLifecycle.CANDIDATE.value
            decision.final_stage = PromotionStage.AUTHORITY.value
            decision.reason = "authority_denied_remain_candidate"
            decision.stages.append(StageResult(
                PromotionStage.PROMOTE, False, "authority_denied_remain_candidate",
                {"authority_id": decision.authority_id},
            ))
            if note:
                decision.notes.append(note)
        return decision

    def _run_hard_gates(self, evidence, checks, stages):
        failures = []

        dq = bool(evidence.get("data_quality_ok", True))
        if evidence.get("hard_rejects"):
            hr = [str(x) for x in evidence["hard_rejects"]]
            if any("DATA" in h.upper() or "QUALITY" in h.upper() for h in hr):
                dq = False
        self._add(checks, stages, "data_validity", GateLayer.HARD, dq,
                  "ok" if dq else "data_quality_failure",
                  PromotionStage.SIGNAL, {"data_quality_ok": dq})
        if not dq:
            failures.append("invalid_data")

        if self.require_feature_ssot:
            feat_ok = bool(
                evidence.get("feature_ssot")
                or evidence.get("feature_snapshot_ok")
                or evidence.get("uses_feature_snapshot")
            )
            if "feature_ssot" not in evidence and "feature_snapshot_ok" not in evidence and "uses_feature_snapshot" not in evidence:
                feat_ok = bool(evidence.get("signal_defined") or evidence.get("strategy_id"))
            self._add(checks, stages, "feature_ssot", GateLayer.HARD, feat_ok,
                      "ok" if feat_ok else "invalid_features",
                      PromotionStage.SIGNAL, {"feature_ssot": feat_ok})
            if not feat_ok:
                failures.append("invalid_features")

        leakage = bool(evidence.get("leakage_detected") or evidence.get("lookahead_detected"))
        pit_ok = bool(evidence.get("lookahead_safe", True)) and not leakage
        if "LOOKAHEAD" in str(evidence.get("hard_rejects") or []):
            pit_ok = False
        self._add(checks, stages, "pit_leakage", GateLayer.HARD, pit_ok,
                  "ok" if pit_ok else "leakage_detected",
                  PromotionStage.SIGNAL, {"lookahead_safe": pit_ok})
        if not pit_ok:
            failures.append("leakage_detected")

        oos = evidence.get("out_of_sample") or {}
        oos_eval = bool(oos.get("evaluated") or evidence.get("oos_evaluated"))
        oos_n = _i(oos.get("n_trades") or evidence.get("oos_n_trades"), 0)
        coverage_ok = oos_eval and oos_n >= self.min_oos_trades
        self._add(checks, stages, "oos_coverage", GateLayer.HARD, coverage_ok,
                  "ok" if coverage_ok else "insufficient_OOS",
                  PromotionStage.OUT_OF_SAMPLE,
                  {"oos_evaluated": oos_eval, "oos_n_trades": oos_n, "min_oos_trades": self.min_oos_trades})
        if not coverage_ok:
            failures.append("insufficient_OOS")

        if self.require_cost_model:
            cost = evidence.get("cost_adjusted") or {}
            cost_ok = bool(
                cost.get("evaluated")
                or evidence.get("cost_evaluated")
                or evidence.get("cost_model")
                or evidence.get("cost_model_id")
            )
            self._add(checks, stages, "cost_model", GateLayer.HARD, cost_ok,
                      "ok" if cost_ok else "cost_model_missing",
                      PromotionStage.COST_ADJUSTED, {"cost_present": cost_ok})
            if not cost_ok:
                failures.append("cost_model_missing")

        hard_rejects = [str(x).upper() for x in (evidence.get("hard_rejects") or [])]
        risk_codes = {"EXCESSIVE_DRAWDOWN", "RISK_VIOLATION", "RISK_LIMIT"}
        risk_ok = not bool(risk_codes & set(hard_rejects))
        if evidence.get("risk_violation"):
            risk_ok = False
        self._add(checks, stages, "risk_constraints", GateLayer.HARD, risk_ok,
                  "ok" if risk_ok else "risk_violation",
                  PromotionStage.BACKTEST, {"hard_rejects": hard_rejects})
        if not risk_ok:
            failures.append("risk_violation")

        repro = evidence.get("reproducibility") or {}
        if "reproducible" in evidence or "reproducible" in repro:
            repro_ok = bool(evidence.get("reproducible", True) and repro.get("reproducible", True))
        else:
            repro_ok = bool(evidence.get("dataset_hash") or evidence.get("reproducible", True))
        if evidence.get("non_reproducible"):
            repro_ok = False
        self._add(checks, stages, "reproducibility", GateLayer.HARD, repro_ok,
                  "ok" if repro_ok else "non_reproducible",
                  PromotionStage.REPRODUCIBILITY, {"dataset_hash": bool(evidence.get("dataset_hash"))})
        if not repro_ok:
            failures.append("non_reproducible")

        if failures:
            return False, "hard_fail:" + ",".join(failures)
        return True, "hard_gates_pass"

    def _run_evidence_gates(self, evidence, checks, stages, notes):
        failures = []

        bt = evidence.get("backtest") or {}
        n_trades = _i(bt.get("closed_trades") or bt.get("n_trades") or evidence.get("n_trades"), 0)
        exp = _f(bt.get("expectancy") or evidence.get("expectancy"), 0.0)
        pf = bt.get("profit_factor")
        pf_v = _f(pf, 0.0) if pf is not None else None
        dd = _f(bt.get("max_drawdown") or evidence.get("max_drawdown"), 0.0)
        if dd > 1.0:
            dd = dd / 100.0

        trades_ok = n_trades >= self.min_trades
        self._add(checks, stages, "min_trades", GateLayer.EVIDENCE, trades_ok,
                  "ok" if trades_ok else f"trades_below_{self.min_trades}",
                  PromotionStage.BACKTEST, {"n_trades": n_trades})
        if not trades_ok:
            failures.append("insufficient_trades")

        cost = evidence.get("cost_adjusted") or {}
        cost_exp = _f(
            cost.get("expectancy_after_cost")
            or cost.get("expectancy")
            or evidence.get("expectancy_after_cost"),
            -1.0,
        )
        if cost_exp < 0 and bool(cost.get("evaluated") or evidence.get("cost_evaluated")):
            cost_exp = exp
        cost_ok = cost_exp >= self.min_expectancy
        self._add(checks, stages, "expectancy_after_cost", GateLayer.EVIDENCE, cost_ok,
                  "ok" if cost_ok else "negative_or_weak_expectancy_after_cost",
                  PromotionStage.COST_ADJUSTED, {"expectancy_after_cost": cost_exp})
        if not cost_ok:
            failures.append("expectancy_after_cost")

        dd_ok = dd <= self.max_drawdown
        self._add(checks, stages, "drawdown", GateLayer.EVIDENCE, dd_ok,
                  "ok" if dd_ok else "drawdown_exceeded",
                  PromotionStage.BACKTEST, {"max_drawdown": dd, "limit": self.max_drawdown})
        if not dd_ok:
            failures.append("drawdown")

        oos = evidence.get("out_of_sample") or {}
        oos_exp = _f(oos.get("expectancy") or evidence.get("oos_expectancy"), 0.0)
        oos_ok = oos_exp >= self.min_oos_expectancy
        self._add(checks, stages, "oos_expectancy", GateLayer.EVIDENCE, oos_ok,
                  "ok" if oos_ok else "oos_expectancy_fail",
                  PromotionStage.OUT_OF_SAMPLE, {"oos_expectancy": oos_exp})
        if not oos_ok:
            failures.append("oos_expectancy")

        wf = evidence.get("walk_forward") or {}
        n_periods = _i(wf.get("n_periods") or evidence.get("wf_n_periods"), 0)
        pass_rate = _f(wf.get("pass_rate") or evidence.get("wf_pass_rate"), 0.0)
        stab = evidence.get("stability") or {}
        sens = _f(stab.get("param_sensitivity") or evidence.get("stability_param_sensitivity"), 1.0)
        wf_ok = n_periods >= self.min_wf_periods and pass_rate >= self.min_wf_pass_rate
        sens_ok = sens <= self.max_param_sensitivity
        stab_ok = wf_ok and sens_ok
        self._add(checks, stages, "stability", GateLayer.EVIDENCE, stab_ok,
                  "ok" if stab_ok else "unstable_across_periods",
                  PromotionStage.STABILITY,
                  {"n_periods": n_periods, "pass_rate": pass_rate, "param_sensitivity": sens})
        if not stab_ok:
            failures.append("stability")

        reg = evidence.get("regime_analysis") or {}
        reg_eval = bool(reg.get("evaluated") or evidence.get("regime_evaluated"))
        not_single = bool(reg.get("not_single_regime_driven", True))
        reg_ok = reg_eval and not_single
        self._add(checks, stages, "regime_robustness", GateLayer.EVIDENCE, reg_ok,
                  "ok" if reg_ok else "regime_not_robust",
                  PromotionStage.REGIME_ANALYSIS,
                  {"evaluated": reg_eval, "not_single_regime_driven": not_single})
        if not reg_ok:
            failures.append("regime")

        if self.require_baseline_comparison:
            base = evidence.get("baseline_comparison") or evidence.get("baseline") or {}
            if not base:
                base_ok = False
                base_reason = "baseline_comparison_missing"
                notes.append("challenger_must_compare_to_baseline_after_cost_oos")
            else:
                base_ok, base_reason = self._baseline_ok(base, notes)
            self._add(checks, stages, "baseline_comparison", GateLayer.EVIDENCE, base_ok,
                      base_reason if not base_ok else "ok",
                      PromotionStage.BASELINE, dict(base) if isinstance(base, dict) else {})
            if not base_ok:
                failures.append("baseline")

        if pf_v is not None and pf_v < self.min_profit_factor:
            failures.append("profit_factor")
            self._add(checks, stages, "profit_factor", GateLayer.EVIDENCE, False,
                      "profit_factor_below_min", PromotionStage.BACKTEST, {"profit_factor": pf_v})

        if failures:
            return False, "evidence_fail:" + ",".join(failures)
        return True, "evidence_gates_pass"

    def _baseline_ok(self, base, notes):
        c_ret = base.get("challenger_oos_return") or base.get("challenger_net_oos_return")
        b_ret = base.get("baseline_oos_return") or base.get("baseline_net_oos_return")
        c_dd = base.get("challenger_max_dd") or base.get("challenger_oos_dd")
        b_dd = base.get("baseline_max_dd") or base.get("baseline_oos_dd")
        stable = bool(base.get("edge_stable_across_periods", False))
        multi_regime = bool(base.get("edge_multi_regime", False))

        if c_ret is None or b_ret is None:
            edge = base.get("net_oos_edge")
            if edge is None:
                return False, "baseline_metrics_incomplete"
            c_ret = _f(edge, 0.0)
            b_ret = 0.0
        else:
            c_ret = _f(c_ret, 0.0)
            b_ret = _f(b_ret, 0.0)

        edge = c_ret - b_ret
        if edge < self.min_baseline_edge:
            notes.append(f"net_oos_edge={edge:.4f}_below_min={self.min_baseline_edge}")
            return False, "baseline_edge_insufficient"

        if c_dd is not None and b_dd is not None:
            c_dd_f, b_dd_f = _f(c_dd), _f(b_dd)
            if c_dd_f > b_dd_f + self.max_baseline_dd_worsen:
                notes.append(f"dd_worsened={c_dd_f - b_dd_f:.4f}")
                return False, "baseline_dd_worsened"

        if edge < 0.03 and not (stable or multi_regime):
            notes.append("small_edge_requires_stability_or_multi_regime")
            return False, "edge_not_stable"

        return True, "ok"

    def _add(self, checks, stages, name, layer, passed, reason, stage, metrics):
        checks.append(GateCheck(
            name=name,
            layer=layer,
            outcome=GateOutcome.PASS if passed else GateOutcome.FAIL,
            reason=reason,
            metrics=metrics,
        ))
        stages.append(StageResult(stage=stage, passed=passed, reason=reason, metrics=metrics))


def evaluate_for_candidacy(strategy_id: str, evidence: dict[str, Any], **kwargs: Any) -> PromotionDecision:
    return PromotionGate(**kwargs).evaluate(strategy_id, evidence)


def promote_with_authority(
    decision: PromotionDecision,
    *,
    authority_id: str,
    approve: bool = True,
    promotion_id: str = "",
    note: str = "",
) -> PromotionDecision:
    return PromotionGate().apply_authority(
        decision,
        authority_id=authority_id,
        approve=approve,
        promotion_id=promotion_id,
        note=note,
    )


# Re-export invariants for tests / external callers
from src.python.strategy.promotion_invariants import (  # noqa: E402
    assert_fill_allowed_for_status,
    assert_promoted_invariants,
    fill_allowed_for_status,
    promoted_record_missing_fields,
)


def evaluate_evidence_package(package: Any, **kwargs: Any) -> PromotionDecision:
    """Wire EvidencePackage (evaluator OOS) → evaluate_for_candidacy."""
    if hasattr(package, "to_promotion_evidence"):
        strategy_id = str(getattr(package, "strategy_id", "") or "unknown")
        evidence = package.to_promotion_evidence()
    elif isinstance(package, dict):
        evidence = package
        strategy_id = str(evidence.get("strategy_id") or "unknown")
    else:
        raise TypeError("evaluate_evidence_package expects EvidencePackage or dict")
    return evaluate_for_candidacy(strategy_id, evidence, **kwargs)
