"""Evidence package — structured metrics for PromotionGate (AND-gate, not cosmetic score)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Optional


class HardRejectCode(str, Enum):
    INSUFFICIENT_TRADES = "INSUFFICIENT_TRADES"
    LOOKAHEAD_DETECTED = "LOOKAHEAD_DETECTED"
    OOS_FAILURE = "OOS_FAILURE"
    COST_ADJUSTED_FAILURE = "COST_ADJUSTED_FAILURE"
    EXCESSIVE_DRAWDOWN = "EXCESSIVE_DRAWDOWN"
    UNSTABLE_WF = "UNSTABLE_WF"
    REGIME_CONCENTRATION = "REGIME_CONCENTRATION"
    DATA_QUALITY_FAILURE = "DATA_QUALITY_FAILURE"
    ZERO_VARIANCE = "ZERO_VARIANCE"
    NEGATIVE_EXPECTANCY = "NEGATIVE_EXPECTANCY"
    INVALID_FEATURES = "INVALID_FEATURES"
    COST_MODEL_MISSING = "COST_MODEL_MISSING"
    RISK_VIOLATION = "RISK_VIOLATION"
    NON_REPRODUCIBLE = "NON_REPRODUCIBLE"
    INSUFFICIENT_OOS = "INSUFFICIENT_OOS"
    NONE = "NONE"


@dataclass
class WindowMetrics:
    window_id: str
    n_trades: int = 0
    total_return: float = 0.0
    expectancy: float = 0.0
    profit_factor: Optional[float] = None
    win_rate: Optional[float] = None
    max_drawdown: float = 0.0
    sharpe: Optional[float] = None
    turnover: float = 0.0
    transaction_cost: float = 0.0
    final_equity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class EvidencePackage:
    """Compatible with PromotionGate.evaluate(strategy_id, evidence_dict).

    Versioned identity for control-plane promotion:
      strategy_id + strategy_version + evidence_id + dataset/feature hashes
    """
    strategy_id: str
    strategy_version: str = "0.0.0"
    evidence_id: str = ""
    dataset_hash: str = ""
    feature_hash: str = ""
    cost_model: str = "simulation_v2"
    evaluation_date: str = ""
    feature_ssot: bool = True
    uses_feature_snapshot: bool = True
    signal_defined: bool = True
    timing: str = "signal_T_execute_open_Tplus1"
    lookahead_safe: bool = True
    data_quality_ok: bool = True
    leakage_detected: bool = False
    reproducible: bool = True

    # aggregate in-sample / full sample
    n_trades: int = 0
    total_return: float = 0.0
    cagr: Optional[float] = None
    sharpe: Optional[float] = None
    sortino: Optional[float] = None
    max_drawdown: float = 0.0
    profit_factor: Optional[float] = None
    expectancy: float = 0.0
    win_rate: Optional[float] = None
    turnover: float = 0.0
    transaction_cost: float = 0.0
    avg_exposure_pct: float = 0.0

    # walk-forward
    wf_n_periods: int = 0
    wf_pass_rate: float = 0.0
    wf_windows: list[WindowMetrics] = field(default_factory=list)
    stability_param_sensitivity: float = 1.0  # lower better; 1.0 = not evaluated

    # OOS
    oos_evaluated: bool = False
    oos_expectancy: float = 0.0
    oos_n_trades: int = 0
    oos_max_drawdown: float = 0.0
    train_to_oos_degradation: Optional[float] = None  # (train_exp - oos_exp) / max(|train|, eps)

    # cost-adjusted (already net of fees in primary path; explicit flag)
    cost_evaluated: bool = True
    expectancy_after_cost: float = 0.0

    # regime
    regime_evaluated: bool = False
    regimes_tested: list[str] = field(default_factory=list)
    regime_trade_share: dict[str, float] = field(default_factory=dict)
    not_single_regime_driven: bool = True

    hard_rejects: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_promotion_evidence(self) -> dict[str, Any]:
        """Shape expected by PromotionGate.evaluate."""
        eid = self.evidence_id or f"EP-{self.strategy_id}-DRAFT"
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "evidence_id": eid,
            "dataset_hash": self.dataset_hash,
            "feature_hash": self.feature_hash,
            "cost_model": self.cost_model,
            "evaluation_date": self.evaluation_date,
            "feature_ssot": self.feature_ssot,
            "feature_snapshot_ok": self.uses_feature_snapshot,
            "uses_feature_snapshot": self.uses_feature_snapshot,
            "signal_defined": self.signal_defined,
            "leakage_detected": self.leakage_detected,
            "reproducible": self.reproducible,
            "backtest": {
                "closed_trades": self.n_trades,
                "n_trades": self.n_trades,
                "expectancy": self.expectancy,
                "profit_factor": self.profit_factor,
                "max_drawdown": self.max_drawdown,
                "total_return": self.total_return,
                "sharpe": self.sharpe,
                "win_rate": self.win_rate,
                "turnover": self.turnover,
                "transaction_cost": self.transaction_cost,
            },
            "walk_forward": {
                "n_periods": self.wf_n_periods,
                "pass_rate": self.wf_pass_rate,
                "windows": [w.to_dict() for w in self.wf_windows],
            },
            "out_of_sample": {
                "evaluated": self.oos_evaluated,
                "expectancy": self.oos_expectancy,
                "n_trades": self.oos_n_trades,
                "max_drawdown": self.oos_max_drawdown,
                "degradation": self.train_to_oos_degradation,
            },
            "cost_adjusted": {
                "evaluated": self.cost_evaluated,
                "expectancy_after_cost": self.expectancy_after_cost,
                "transaction_cost": self.transaction_cost,
            },
            "stability": {
                "evaluated": self.wf_n_periods > 0,
                "param_sensitivity": self.stability_param_sensitivity,
                "wf_pass_rate": self.wf_pass_rate,
            },
            "regime_analysis": {
                "evaluated": self.regime_evaluated,
                "regimes_tested": self.regimes_tested,
                "regime_trade_share": self.regime_trade_share,
                "not_single_regime_driven": self.not_single_regime_driven,
            },
            "hard_rejects": list(self.hard_rejects),
            "lookahead_safe": self.lookahead_safe,
            "data_quality_ok": self.data_quality_ok,
            "timing": self.timing,
        }

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["wf_windows"] = [w.to_dict() for w in self.wf_windows]
        return d
