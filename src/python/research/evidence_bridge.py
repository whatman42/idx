"""ExperimentResult → EvidencePackage (first-class) → PromotionGate candidacy.

Never auto-promotes. Never mutates Champion.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.python.research.experiment_result import ExperimentResult
from src.python.strategy.evidence import EvidencePackage, HardRejectCode, WindowMetrics
from src.python.strategy.evidence_freeze import freeze_evidence_package
from src.python.strategy.promotion_gate import PromotionGate, PromotionDecision


def experiment_result_to_evidence_package(result: ExperimentResult) -> EvidencePackage:
    """Convert immutable ExperimentResult into strategy.evidence.EvidencePackage."""
    oos = (result.metrics or {}).get("oos") or {}
    status = result.status
    hard: list[str] = []
    notes: list[str] = [
        f"experiment_id={result.experiment_id}",
        f"job_id={result.job_id}",
        f"result_hash={result.result_hash}",
        f"selection_split={result.selection_split}",
        f"selection_rule={result.selection_rule}",
        f"n_trials={result.number_of_trials}",
        f"n_candidates={result.number_of_candidates}",
        "source=research.wfa_executor",
        "auto_promote=false",
    ]

    leakage = result.leakage_checks or {}
    integrity = result.integrity_checks or {}
    robust = result.robustness or {}

    lookahead_safe = bool(leakage.get("pit_ok", True)) and not leakage.get("future_cols")
    if not lookahead_safe or leakage.get("future_cols"):
        hard.append(HardRejectCode.LOOKAHEAD_DETECTED.value)
        lookahead_safe = False

    if integrity.get("fail_reason"):
        reason = str(integrity.get("fail_reason"))
        if "cost_model" in reason:
            hard.append(HardRejectCode.COST_MODEL_MISSING.value)
        if "lookahead" in reason:
            hard.append(HardRejectCode.LOOKAHEAD_DETECTED.value)
        notes.append(f"fail_reason={reason}")

    n_oos = int(oos.get("n_trades") or 0)
    oos_exp = float(oos.get("expectancy") or 0.0)
    oos_dd = float(oos.get("max_drawdown") or 0.0)
    oos_ret = float(oos.get("total_return") or 0.0)
    oos_pf = oos.get("profit_factor")
    oos_wr = oos.get("win_rate")
    oos_sharpe = oos.get("sharpe")

    if status in ("FAILED", "INVALID"):
        if HardRejectCode.LOOKAHEAD_DETECTED.value not in hard:
            hard.append(HardRejectCode.DATA_QUALITY_FAILURE.value)
    if status == "INSUFFICIENT_EVIDENCE" or n_oos < 5:
        hard.append(HardRejectCode.INSUFFICIENT_OOS.value)
        hard.append(HardRejectCode.INSUFFICIENT_TRADES.value)
    if oos_exp < 0 and status not in ("FAILED", "INVALID"):
        hard.append(HardRejectCode.NEGATIVE_EXPECTANCY.value)
    if robust.get("overfit_risk"):
        hard.append(HardRejectCode.UNSTABLE_WF.value)
        notes.append("OVERFIT_RISK")
    if status == "FRAGILE":
        hard.append(HardRejectCode.UNSTABLE_WF.value)
        notes.append("robustness=FRAGILE")
    if not result.configuration_fingerprint or not result.result_hash:
        hard.append(HardRejectCode.NON_REPRODUCIBLE.value)

    wf_windows: list[WindowMetrics] = []
    for w in result.windows or []:
        m = w.get("metrics_oos") or {}
        wf_windows.append(WindowMetrics(
            window_id=str(w.get("window_id", "")),
            n_trades=int(m.get("n_trades") or 0),
            total_return=float(m.get("total_return") or 0.0),
            expectancy=float(m.get("expectancy") or 0.0),
            profit_factor=m.get("profit_factor"),
            win_rate=m.get("win_rate"),
            max_drawdown=float(m.get("max_drawdown") or 0.0),
            sharpe=m.get("sharpe"),
            transaction_cost=float(m.get("fees_paid") or 0.0),
        ))
    n_pass = sum(1 for w in wf_windows if (w.expectancy or 0) > 0)
    wf_pass = (n_pass / len(wf_windows)) if wf_windows else 0.0
    if wf_windows and wf_pass < 0.5 and HardRejectCode.UNSTABLE_WF.value not in hard:
        hard.append(HardRejectCode.UNSTABLE_WF.value)

    stress = robust.get("stress") or []
    param_sens = 1.0
    if stress:
        exps = [float(s.get("expectancy") or 0) for s in stress]
        param_sens = float(max(exps) - min(exps)) if exps else 1.0

    sid = (result.challenger_version or "challenger").split("@")[0] or "challenger"
    sver = result.challenger_version if "@" in (result.challenger_version or "") else f"{sid}@research"

    pkg = EvidencePackage(
        strategy_id=sid,
        strategy_version=sver,
        evidence_id=f"EVD-{result.experiment_id}",
        dataset_hash=result.dataset_hash or "",
        feature_hash=result.feature_hash or "",
        cost_model=result.cost_model or "simulation_v2",
        evaluation_date=result.created_at or datetime.now(timezone.utc).isoformat(),
        feature_ssot=True,
        uses_feature_snapshot=True,
        signal_defined=True,
        timing="signal_T_execute_open_Tplus1",
        lookahead_safe=lookahead_safe,
        data_quality_ok=status not in ("FAILED", "INVALID"),
        leakage_detected=not lookahead_safe,
        reproducible=bool(result.result_hash and result.configuration_fingerprint),
        n_trades=n_oos,
        total_return=oos_ret,
        sharpe=oos_sharpe if isinstance(oos_sharpe, (int, float)) else None,
        max_drawdown=oos_dd,
        profit_factor=oos_pf if isinstance(oos_pf, (int, float)) else None,
        expectancy=oos_exp,
        win_rate=oos_wr if isinstance(oos_wr, (int, float)) else None,
        transaction_cost=float(oos.get("fees_paid") or 0.0),
        wf_n_periods=len(wf_windows),
        wf_pass_rate=wf_pass,
        wf_windows=wf_windows,
        stability_param_sensitivity=param_sens,
        oos_evaluated=True,
        oos_expectancy=oos_exp,
        oos_n_trades=n_oos,
        oos_max_drawdown=oos_dd,
        cost_evaluated=True,
        expectancy_after_cost=oos_exp,
        hard_rejects=list(dict.fromkeys(hard)),
        notes=notes,
    )
    return freeze_evidence_package(pkg)


def experiment_result_to_evidence(result: ExperimentResult) -> dict[str, Any]:
    """Backward-compatible: EvidencePackage.to_promotion_evidence() + research metadata."""
    pkg = experiment_result_to_evidence_package(result)
    d = pkg.to_promotion_evidence()
    d.update({
        "walk_forward_executed": True,
        "cost_model_id": result.cost_model,
        "fee_buy_bps": result.cost_model_detail.get("fee_bps", 15.0),
        "fee_exit_bps": result.cost_model_detail.get("exit_fee_bps", 25.0),
        "slippage_bps": result.cost_model_detail.get("slippage_bps", 5.0),
        "commit_sha": result.commit_sha,
        "seed": result.seed,
        "configuration_fingerprint": result.configuration_fingerprint,
        "result_hash": result.result_hash,
        "selection_split": result.selection_split,
        "selection_rule": result.selection_rule,
        "number_of_trials": result.number_of_trials,
        "number_of_candidates": result.number_of_candidates,
        "status": result.status,
        "robustness": result.robustness,
        "auto_promote": False,
        "approved": False,
    })
    return d


def evaluate_research_candidacy(
    result: ExperimentResult,
    *,
    gate: Optional[PromotionGate] = None,
) -> dict[str, Any]:
    """Run PromotionGate on validated EvidencePackage. Research path never approves.

    Fail-closed: provenance / anti-overfit / tamper / integrity failures block candidacy.
    """
    from src.python.research.invariants import (
        assert_research_cannot_promote,
        check_anti_overfit_gate,
        check_evidence_package,
        check_no_oos_tuning,
        check_result_provenance,
        check_tamper,
    )

    blocked: list[str] = []
    ok, reason = check_result_provenance(result)
    if not ok:
        blocked.append(reason)
    ok, reason = check_no_oos_tuning(result)
    if not ok:
        blocked.append(reason)
    ok, reason = check_anti_overfit_gate(result)
    if not ok:
        blocked.append(reason)
    ok, reason = check_tamper(result)
    if not ok:
        blocked.append(reason)

    pkg = experiment_result_to_evidence_package(result)
    ok, reason = check_evidence_package(pkg)
    if not ok:
        blocked.append(reason)

    if blocked:
        return {
            "approved": False,
            "candidacy": False,
            "research_path": True,
            "production_mutation": False,
            "blocked": True,
            "block_reasons": blocked,
            "evidence_id": pkg.evidence_id,
            "hard_rejects": list(pkg.hard_rejects),
            "status": result.status,
            "reason": "research_invariants_failed:" + ",".join(blocked[:5]),
        }

    evidence = pkg.to_promotion_evidence()
    evidence["auto_promote"] = False
    g = gate or PromotionGate()
    decision: PromotionDecision = g.evaluate(pkg.strategy_id, evidence)
    out = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision.__dict__)
    out["approved"] = False
    out["research_path"] = True
    out["production_mutation"] = False
    out["evidence_id"] = pkg.evidence_id
    out["hard_rejects"] = list(pkg.hard_rejects)
    out["blocked"] = False
    out["evidence_package"] = pkg.to_dict() if hasattr(pkg, "to_dict") else evidence
    assert_research_cannot_promote(out)
    return out
