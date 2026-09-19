"""Promotion Gate control-plane: hard / evidence / authority layers."""
from __future__ import annotations

from src.python.strategy.promotion_gate import (
    PromotionGate,
    evaluate_for_candidacy,
    promote_with_authority,
)
from src.python.strategy.contracts import StrategyLifecycle
from src.python.strategy.production_control import assert_production_allowed, eligibility


def _base_evidence(**over):
    ev = {
        "strategy_id": "trend_multi",
        "strategy_version": "2.3.1",
        "evidence_id": "EP-2026-0919-004",
        "dataset_hash": "abc123",
        "feature_hash": "feat456",
        "cost_model": "simulation_v2",
        "evaluation_date": "2026-09-19",
        "signal_defined": True,
        "feature_ssot": True,
        "uses_feature_snapshot": True,
        "lookahead_safe": True,
        "data_quality_ok": True,
        "reproducible": True,
        "backtest": {
            "n_trades": 91,
            "expectancy": 0.02,
            "profit_factor": 1.3,
            "max_drawdown": 0.074,
        },
        "walk_forward": {"n_periods": 4, "pass_rate": 0.75},
        "out_of_sample": {
            "evaluated": True,
            "expectancy": 0.015,
            "n_trades": 40,
            "max_drawdown": 0.074,
        },
        "cost_adjusted": {"evaluated": True, "expectancy_after_cost": 0.012},
        "stability": {"evaluated": True, "param_sensitivity": 0.3},
        "regime_analysis": {
            "evaluated": True,
            "not_single_regime_driven": True,
            "regimes_tested": ["bull", "neutral"],
        },
        "baseline_comparison": {
            "challenger_oos_return": 0.104,
            "baseline_oos_return": 0.082,
            "challenger_max_dd": 0.074,
            "baseline_max_dd": 0.071,
            "edge_stable_across_periods": True,
            "edge_multi_regime": True,
        },
    }
    ev.update(over)
    return ev


def test_hard_gate_rejects_leakage():
    gate = PromotionGate()
    d = gate.evaluate("trend_multi", _base_evidence(lookahead_safe=False, leakage_detected=True))
    assert d.lifecycle_status == StrategyLifecycle.REJECTED.value
    assert d.hard_passed is False
    assert "leakage" in d.reason


def test_hard_gate_rejects_insufficient_oos():
    d = PromotionGate().evaluate(
        "trend_multi",
        _base_evidence(out_of_sample={"evaluated": True, "expectancy": 0.01, "n_trades": 5}),
    )
    assert d.lifecycle_status == StrategyLifecycle.REJECTED.value
    assert "insufficient_OOS" in d.reason


def test_evidence_fail_stays_evaluated_not_promoted():
    d = PromotionGate().evaluate(
        "trend_multi",
        _base_evidence(baseline_comparison={}),
    )
    assert d.hard_passed is True
    assert d.evidence_passed is False
    assert d.approved is False
    assert d.lifecycle_status == StrategyLifecycle.EVALUATED.value


def test_small_edge_without_stability_fails_baseline():
    d = PromotionGate().evaluate(
        "trend_multi",
        _base_evidence(
            baseline_comparison={
                "challenger_oos_return": 0.090,
                "baseline_oos_return": 0.082,
                "challenger_max_dd": 0.074,
                "baseline_max_dd": 0.071,
                "edge_stable_across_periods": False,
                "edge_multi_regime": False,
            }
        ),
    )
    assert d.approved is False
    assert d.candidacy is False


def test_full_evidence_yields_candidate_not_promoted():
    d = evaluate_for_candidacy("trend_multi", _base_evidence())
    assert d.hard_passed and d.evidence_passed and d.candidacy
    assert d.approved is False
    assert d.lifecycle_status == StrategyLifecycle.CANDIDATE.value
    assert d.authority_required is True


def test_authority_required_for_promoted():
    d = evaluate_for_candidacy("trend_multi", _base_evidence())
    d2 = promote_with_authority(d, authority_id="ops-lead-2026", approve=True, promotion_id="PROM-2026-0919-002")
    assert d2.approved is True
    assert d2.lifecycle_status == StrategyLifecycle.PROMOTED.value
    assert d2.promotion_id == "PROM-2026-0919-002"
    assert d2.authority_id == "ops-lead-2026"


def test_authority_reject():
    d = evaluate_for_candidacy("trend_multi", _base_evidence())
    d2 = promote_with_authority(d, authority_id="ops-lead", approve=False, note="edge_not_worth_complexity")
    assert d2.lifecycle_status == StrategyLifecycle.REJECTED.value
    assert d2.approved is False


def test_cannot_authority_promote_without_candidate():
    d = PromotionGate().evaluate("trend_multi", _base_evidence(lookahead_safe=False, leakage_detected=True))
    d2 = promote_with_authority(d, authority_id="ops", approve=True)
    assert d2.approved is False
    assert "non_candidate" in d2.reason or d2.lifecycle_status != StrategyLifecycle.PROMOTED.value


def test_production_control_blocks_candidate():
    e = eligibility("trend_multi")
    assert e.production_allowed is False
    try:
        assert_production_allowed("trend_multi")
        assert False
    except RuntimeError:
        pass
    assert eligibility("rule_sma20").production_allowed is True


def test_no_single_score_path():
    gate = PromotionGate()
    assert not hasattr(gate, "score_threshold")
    d = gate.evaluate("trend_multi", _base_evidence())
    assert d.approved is False or d.candidacy
