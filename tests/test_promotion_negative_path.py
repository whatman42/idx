"""Negative-path promotion + fill matrix + promoted invariants + immutable audit."""
from __future__ import annotations

import pytest

from src.python.strategy.contracts import StrategyLifecycle
from src.python.strategy.evidence import EvidencePackage
from src.python.strategy.promotion_audit import PromotionAuditLog
from src.python.strategy.promotion_gate import (
    assert_fill_allowed_for_status,
    assert_promoted_invariants,
    evaluate_evidence_package,
    evaluate_for_candidacy,
    fill_allowed_for_status,
    promote_with_authority,
    promoted_record_missing_fields,
)
from src.python.strategy.production_control import assert_production_allowed, eligibility


def _good_evidence(**over):
    ev = {
        "strategy_id": "trend_multi",
        "strategy_version": "2.3.1",
        "evidence_id": "EP-2026-0919-004",
        "dataset_hash": "ds-abc",
        "feature_hash": "ft-xyz",
        "cost_model": "simulation_v2",
        "evaluation_date": "2026-09-19",
        "signal_defined": True,
        "feature_ssot": True,
        "uses_feature_snapshot": True,
        "lookahead_safe": True,
        "data_quality_ok": True,
        "reproducible": True,
        "backtest": {"n_trades": 91, "expectancy": 0.02, "profit_factor": 1.3, "max_drawdown": 0.074},
        "walk_forward": {"n_periods": 4, "pass_rate": 0.75},
        "out_of_sample": {"evaluated": True, "expectancy": 0.015, "n_trades": 40, "max_drawdown": 0.074},
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


@pytest.mark.parametrize(
    "status,allowed",
    [
        ("RESEARCH", False),
        ("EVALUATED", False),
        ("CANDIDATE", False),
        ("REJECTED", False),
        ("RETIRED", False),
        ("PROMOTED", True),
    ],
)
def test_fill_matrix_by_status(status, allowed):
    assert fill_allowed_for_status(status) is allowed
    if allowed:
        assert_fill_allowed_for_status(status)
    else:
        with pytest.raises(RuntimeError, match="fill_blocked"):
            assert_fill_allowed_for_status(status)


def test_registry_research_cannot_fill():
    assert eligibility("trend_multi").production_allowed is False
    with pytest.raises(RuntimeError, match="production_blocked"):
        assert_production_allowed("trend_multi")


def test_registry_promoted_can_fill():
    assert eligibility("rule_sma20").production_allowed is True
    assert_production_allowed("rule_sma20")


def test_candidate_approve_false_not_promoted():
    d = evaluate_for_candidacy("trend_multi", _good_evidence())
    assert d.lifecycle_status == StrategyLifecycle.CANDIDATE.value
    d2 = promote_with_authority(d, authority_id="ops-lead", approve=False, note="hold")
    assert d2.approved is False
    assert d2.lifecycle_status == StrategyLifecycle.CANDIDATE.value
    assert fill_allowed_for_status(d2.lifecycle_status) is False


def test_candidate_missing_authority_id_not_promoted():
    d = evaluate_for_candidacy("trend_multi", _good_evidence())
    d2 = promote_with_authority(d, authority_id="", approve=True)
    assert d2.approved is False
    assert d2.lifecycle_status != StrategyLifecycle.PROMOTED.value


def test_invalid_evidence_not_promoted():
    d = evaluate_for_candidacy(
        "trend_multi",
        _good_evidence(lookahead_safe=False, leakage_detected=True),
    )
    assert d.lifecycle_status == StrategyLifecycle.REJECTED.value
    d2 = promote_with_authority(d, authority_id="ops", approve=True)
    assert d2.approved is False
    assert d2.lifecycle_status != StrategyLifecycle.PROMOTED.value


def test_promoted_has_required_identity_fields():
    d = evaluate_for_candidacy("trend_multi", _good_evidence())
    d2 = promote_with_authority(
        d,
        authority_id="ops-lead-2026",
        approve=True,
        promotion_id="PROM-2026-0919-002",
    )
    assert d2.lifecycle_status == StrategyLifecycle.PROMOTED.value
    assert_promoted_invariants(d2)
    assert not promoted_record_missing_fields(d2)
    for field in (
        "promotion_id", "authority_id", "evidence_id", "strategy_version",
        "dataset_hash", "feature_hash", "cost_model", "baseline_id",
    ):
        assert getattr(d2, field), field


def test_promoted_invariant_fails_without_hashes():
    d = evaluate_for_candidacy(
        "trend_multi",
        _good_evidence(dataset_hash="", feature_hash=""),
    )
    d2 = promote_with_authority(d, authority_id="ops", approve=True, promotion_id="PROM-X")
    assert d2.lifecycle_status != StrategyLifecycle.PROMOTED.value or not d2.approved
    assert d2.approved is False


def test_evaluate_evidence_package_from_oos():
    pkg = EvidencePackage(
        strategy_id="trend_multi",
        strategy_version="2.3.1",
        evidence_id="EP-2026-0919-004",
        dataset_hash="ds-abc",
        feature_hash="ft-xyz",
        cost_model="simulation_v2",
        evaluation_date="2026-09-19",
        feature_ssot=True,
        uses_feature_snapshot=True,
        signal_defined=True,
        lookahead_safe=True,
        data_quality_ok=True,
        reproducible=True,
        n_trades=91,
        expectancy=0.02,
        profit_factor=1.3,
        max_drawdown=0.074,
        wf_n_periods=4,
        wf_pass_rate=0.75,
        oos_evaluated=True,
        oos_expectancy=0.015,
        oos_n_trades=40,
        oos_max_drawdown=0.074,
        cost_evaluated=True,
        expectancy_after_cost=0.012,
        stability_param_sensitivity=0.3,
        regime_evaluated=True,
        not_single_regime_driven=True,
        regimes_tested=["bull", "neutral"],
    )
    evidence = pkg.to_promotion_evidence()
    evidence["baseline_comparison"] = {
        "challenger_oos_return": 0.104,
        "baseline_oos_return": 0.082,
        "challenger_max_dd": 0.074,
        "baseline_max_dd": 0.071,
        "edge_stable_across_periods": True,
        "edge_multi_regime": True,
    }
    d = evaluate_evidence_package(evidence)
    assert d.hard_passed is True
    assert d.candidacy is True
    assert d.lifecycle_status == StrategyLifecycle.CANDIDATE.value
    assert d.approved is False


def test_audit_append_only_and_version_bump():
    log = PromotionAuditLog()
    d = evaluate_for_candidacy("trend_multi", _good_evidence())
    d2 = promote_with_authority(
        d, authority_id="ops-lead", approve=True, promotion_id="PROM-2026-0919-002",
    )
    assert d2.approved
    rec1 = log.append(d2)
    assert rec1.strategy_version == "2.3.1"
    with pytest.raises(RuntimeError, match="immutable_violation"):
        log.append(d2)
    d3 = evaluate_for_candidacy(
        "trend_multi",
        _good_evidence(strategy_version="2.3.2", evidence_id="EP-2026-0919-005"),
    )
    d4 = promote_with_authority(
        d3, authority_id="ops-lead", approve=True, promotion_id="PROM-2026-0919-003",
    )
    rec2 = log.append(d4)
    assert rec2.strategy_version == "2.3.2"
    rows = log.list_for_strategy("trend_multi")
    assert len(rows) == 2
    assert rows[0].strategy_version == "2.3.1"
    assert rows[1].strategy_version == "2.3.2"
