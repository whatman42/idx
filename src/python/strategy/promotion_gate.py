"""Promotion contract — no strategy reaches production without staged evidence.

Pipeline:
  Signal → Backtest → Walk-forward → Out-of-sample → Cost adjustment
  → Stability test → Regime analysis → Promote

Default is REJECT. Explicit metrics must clear every stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class PromotionStage(str, Enum):
    SIGNAL = "SIGNAL"
    BACKTEST = "BACKTEST"
    WALK_FORWARD = "WALK_FORWARD"
    OUT_OF_SAMPLE = "OUT_OF_SAMPLE"
    COST_ADJUSTED = "COST_ADJUSTED"
    STABILITY = "STABILITY"
    REGIME_ANALYSIS = "REGIME_ANALYSIS"
    PROMOTE = "PROMOTE"


STAGE_ORDER: tuple[PromotionStage, ...] = (
    PromotionStage.SIGNAL,
    PromotionStage.BACKTEST,
    PromotionStage.WALK_FORWARD,
    PromotionStage.OUT_OF_SAMPLE,
    PromotionStage.COST_ADJUSTED,
    PromotionStage.STABILITY,
    PromotionStage.REGIME_ANALYSIS,
    PromotionStage.PROMOTE,
)


@dataclass
class StageResult:
    stage: PromotionStage
    passed: bool
    reason: str
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class PromotionVerdict:
    strategy_id: str
    approved: bool
    final_stage: PromotionStage
    stages: list[StageResult]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "approved": self.approved,
            "final_stage": self.final_stage.value,
            "reason": self.reason,
            "stages": [
                {"stage": s.stage.value, "passed": s.passed, "reason": s.reason, "metrics": s.metrics}
                for s in self.stages
            ],
        }


class PromotionGate:
    """Evaluate strategy evidence package. Never promote by default."""

    def __init__(
        self,
        *,
        min_trades: int = 30,
        min_expectancy: float = 0.0,
        min_profit_factor: float = 1.0,
        max_drawdown: float = 0.25,
        min_wf_periods: int = 3,
        min_oos_expectancy: float = 0.0,
        max_param_sensitivity: float = 0.5,
    ):
        self.min_trades = min_trades
        self.min_expectancy = min_expectancy
        self.min_profit_factor = min_profit_factor
        self.max_drawdown = max_drawdown
        self.min_wf_periods = min_wf_periods
        self.min_oos_expectancy = min_oos_expectancy
        self.max_param_sensitivity = max_param_sensitivity

    def evaluate(self, strategy_id: str, evidence: dict[str, Any]) -> PromotionVerdict:
        stages: list[StageResult] = []

        # SIGNAL — has defined signal contract
        has_signal = bool(evidence.get("signal_defined") or evidence.get("strategy_id"))
        stages.append(StageResult(
            PromotionStage.SIGNAL,
            has_signal,
            "ok" if has_signal else "missing_signal_contract",
            {"signal_defined": has_signal},
        ))
        if not has_signal:
            return self._reject(strategy_id, stages, PromotionStage.SIGNAL, "missing_signal_contract")

        # BACKTEST
        bt = evidence.get("backtest") or {}
        n_trades = int(bt.get("closed_trades") or bt.get("n_trades") or 0)
        exp = float(bt.get("expectancy") or 0.0)
        pf = bt.get("profit_factor")
        pf_v = float(pf) if pf is not None else None
        dd = float(bt.get("max_drawdown") or bt.get("max_drawdown_pct", 0) / 100.0 or 0.0)
        if dd > 1.0:  # allow percent form
            dd = dd / 100.0
        bt_ok = (
            n_trades >= self.min_trades
            and exp >= self.min_expectancy
            and (pf_v is None or pf_v >= self.min_profit_factor)
            and dd <= self.max_drawdown
        )
        reason = "ok"
        if n_trades < self.min_trades:
            reason = f"trades_below_{self.min_trades}"
        elif exp < self.min_expectancy:
            reason = "expectancy_non_positive"
        elif pf_v is not None and pf_v < self.min_profit_factor:
            reason = "profit_factor_below_min"
        elif dd > self.max_drawdown:
            reason = "drawdown_exceeded"
        stages.append(StageResult(
            PromotionStage.BACKTEST, bt_ok, reason,
            {"n_trades": n_trades, "expectancy": exp, "profit_factor": pf_v, "max_drawdown": dd},
        ))
        if not bt_ok:
            return self._reject(strategy_id, stages, PromotionStage.BACKTEST, reason)

        # WALK_FORWARD
        wf = evidence.get("walk_forward") or {}
        n_periods = int(wf.get("n_periods") or 0)
        wf_pass_rate = float(wf.get("pass_rate") or 0.0)
        wf_ok = n_periods >= self.min_wf_periods and wf_pass_rate >= 0.5
        wf_reason = "ok" if wf_ok else (
            f"wf_periods_below_{self.min_wf_periods}" if n_periods < self.min_wf_periods else "wf_pass_rate_below_0.5"
        )
        stages.append(StageResult(
            PromotionStage.WALK_FORWARD, wf_ok, wf_reason,
            {"n_periods": n_periods, "pass_rate": wf_pass_rate},
        ))
        if not wf_ok:
            return self._reject(strategy_id, stages, PromotionStage.WALK_FORWARD, wf_reason)

        # OUT_OF_SAMPLE
        oos = evidence.get("out_of_sample") or {}
        oos_exp = float(oos.get("expectancy") or 0.0)
        oos_ok = bool(oos.get("evaluated")) and oos_exp >= self.min_oos_expectancy
        oos_reason = "ok" if oos_ok else ("oos_not_evaluated" if not oos.get("evaluated") else "oos_expectancy_fail")
        stages.append(StageResult(
            PromotionStage.OUT_OF_SAMPLE, oos_ok, oos_reason,
            {"expectancy": oos_exp, "evaluated": bool(oos.get("evaluated"))},
        ))
        if not oos_ok:
            return self._reject(strategy_id, stages, PromotionStage.OUT_OF_SAMPLE, oos_reason)

        # COST_ADJUSTED
        cost = evidence.get("cost_adjusted") or {}
        cost_exp = float(cost.get("expectancy_after_cost") or cost.get("expectancy") or -1.0)
        cost_ok = bool(cost.get("evaluated")) and cost_exp >= self.min_expectancy
        cost_reason = "ok" if cost_ok else (
            "cost_not_evaluated" if not cost.get("evaluated") else "cost_adjusted_expectancy_fail"
        )
        stages.append(StageResult(
            PromotionStage.COST_ADJUSTED, cost_ok, cost_reason,
            {"expectancy_after_cost": cost_exp},
        ))
        if not cost_ok:
            return self._reject(strategy_id, stages, PromotionStage.COST_ADJUSTED, cost_reason)

        # STABILITY
        stab = evidence.get("stability") or {}
        sens = float(stab.get("param_sensitivity") or 1.0)
        stab_ok = bool(stab.get("evaluated")) and sens <= self.max_param_sensitivity
        stab_reason = "ok" if stab_ok else (
            "stability_not_evaluated" if not stab.get("evaluated") else "param_sensitivity_too_high"
        )
        stages.append(StageResult(
            PromotionStage.STABILITY, stab_ok, stab_reason,
            {"param_sensitivity": sens},
        ))
        if not stab_ok:
            return self._reject(strategy_id, stages, PromotionStage.STABILITY, stab_reason)

        # REGIME_ANALYSIS
        reg = evidence.get("regime_analysis") or {}
        reg_ok = bool(reg.get("evaluated")) and bool(reg.get("not_single_regime_driven", True))
        reg_reason = "ok" if reg_ok else (
            "regime_not_evaluated" if not reg.get("evaluated") else "performance_single_regime_only"
        )
        stages.append(StageResult(
            PromotionStage.REGIME_ANALYSIS, reg_ok, reg_reason,
            {"regimes_tested": reg.get("regimes_tested"), "not_single_regime_driven": reg.get("not_single_regime_driven")},
        ))
        if not reg_ok:
            return self._reject(strategy_id, stages, PromotionStage.REGIME_ANALYSIS, reg_reason)

        # PROMOTE
        stages.append(StageResult(PromotionStage.PROMOTE, True, "all_stages_passed", {}))
        return PromotionVerdict(
            strategy_id=strategy_id,
            approved=True,
            final_stage=PromotionStage.PROMOTE,
            stages=stages,
            reason="promoted",
        )

    def _reject(
        self,
        strategy_id: str,
        stages: list[StageResult],
        final: PromotionStage,
        reason: str,
    ) -> PromotionVerdict:
        return PromotionVerdict(
            strategy_id=strategy_id,
            approved=False,
            final_stage=final,
            stages=stages,
            reason=reason,
        )
