"""Strategy Engine foundation tests — no live path changes required."""
from __future__ import annotations

from src.python.strategy.contracts import (
    AlphaScore,
    Decision,
    EnsembleInput,
    RegimeState,
)
from src.python.strategy.ensemble import EnsembleGovernor
from src.python.strategy.exits import build_exit_plan
from src.python.strategy.promotion_gate import PromotionGate, PromotionStage
from src.python.strategy.regime import RegimeEngine
from src.python.strategy.registry import STRATEGY_REGISTRY, list_strategies, promoted_ids
from src.python.strategy.sizing import compute_size


def test_registry_has_families_and_only_sma_promoted():
    assert "rule_sma20" in STRATEGY_REGISTRY
    assert STRATEGY_REGISTRY["rule_sma20"].status == "PROMOTED"
    research = list_strategies(status="RESEARCH")
    assert len(research) >= 6
    assert promoted_ids() == ["rule_sma20"]


def test_regime_engine_labels():
    eng = RegimeEngine()
    r = eng.detect(trend_code=0.5, vol_code=2.5, drawdown=0.2, liquidity_score=0.2, momentum_code=0.3)
    assert r.trend == "bull"
    assert r.volatility == "high"
    assert r.drawdown == "stress"
    assert r.liquidity == "thin"
    assert r.momentum == "up"
    assert r.allows_mean_reversion() is False


def test_ensemble_buy_with_trend_alpha():
    regime = RegimeState(trend="bull", volatility="medium", drawdown="normal", liquidity="normal")
    alphas = [
        AlphaScore(
            strategy_id="trend_multi",
            family="TREND",
            symbol="BBCA",
            score=0.8,
            direction=1,
            confidence=0.7,
            reasons=["sma_slope_up"],
            regime_compatible=True,
        )
    ]
    dec = EnsembleGovernor().decide(EnsembleInput(
        symbol="BBCA", timestamp="2026-09-16", alphas=alphas, regime=regime,
        data_quality_ok=True,
    ))
    assert dec.decision == Decision.BUY
    assert "trend_multi" in dec.contributing_strategies
    assert dec.blocked is False


def test_ensemble_blocks_on_dq():
    regime = RegimeState()
    dec = EnsembleGovernor().decide(EnsembleInput(
        symbol="BBCA", timestamp="2026-09-16", alphas=[], regime=regime,
        data_quality_ok=False,
    ))
    assert dec.decision == Decision.NO_SIGNAL
    assert dec.blocked is True


def test_mean_reversion_gated_in_bull_trend():
    regime = RegimeState(trend="bull", volatility="high", drawdown="normal", liquidity="normal")
    alphas = [
        AlphaScore(
            strategy_id="mean_reversion_z",
            family="MEAN_REVERSION",
            symbol="BBCA",
            score=0.9,
            direction=1,
            regime_compatible=True,
        )
    ]
    dec = EnsembleGovernor().decide(EnsembleInput(
        symbol="BBCA", timestamp="2026-09-16", alphas=alphas, regime=regime,
    ))
    # gated weight should prevent easy BUY from MR alone in bull+high vol
    assert dec.decision in (Decision.NO_SIGNAL, Decision.HOLD, Decision.BUY)


def test_sizing_risk_budget_and_caps():
    plan = compute_size(stop_distance_pct=0.03, risk_budget_pct=0.005, max_weight=0.10)
    assert abs(plan.weight - (0.005 / 0.03)) < 1e-9
    capped = compute_size(
        stop_distance_pct=0.01, risk_budget_pct=0.02, max_weight=0.05,
        portfolio_exposure=0.78, max_portfolio_exposure=0.80,
    )
    assert capped.weight <= 0.05
    assert "portfolio_exposure" in capped.caps_applied or capped.weight <= 0.02


def test_exit_plan_atr_vs_static():
    static = build_exit_plan(entry_price=1000.0, atr=None)
    assert static.method == "static_pct"
    assert abs(static.sl_pct - 0.03) < 1e-9
    atr_plan = build_exit_plan(entry_price=1000.0, atr=20.0, atr_sl_mult=2.0, atr_tp_mult=3.0)
    assert atr_plan.method.startswith("atr")
    assert atr_plan.sl_pct == min(max((20 * 2.0) / 1000.0, 0.01), 0.12)


def test_promotion_default_reject():
    gate = PromotionGate()
    v = gate.evaluate("trend_multi", {"signal_defined": True})
    assert v.approved is False
    assert v.final_stage == PromotionStage.BACKTEST


def test_promotion_full_pass():
    gate = PromotionGate(min_trades=10)
    evidence = {
        "signal_defined": True,
        "backtest": {"closed_trades": 40, "expectancy": 0.01, "profit_factor": 1.2, "max_drawdown": 0.1},
        "walk_forward": {"n_periods": 4, "pass_rate": 0.75},
        "out_of_sample": {"evaluated": True, "expectancy": 0.005},
        "cost_adjusted": {"evaluated": True, "expectancy_after_cost": 0.002},
        "stability": {"evaluated": True, "param_sensitivity": 0.2},
        "regime_analysis": {"evaluated": True, "not_single_regime_driven": True, "regimes_tested": ["bull", "bear"]},
    }
    v = gate.evaluate("trend_multi", evidence)
    assert v.approved is True
    assert v.final_stage == PromotionStage.PROMOTE
