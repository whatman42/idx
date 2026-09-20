"""Regression: learning.contracts must remain the public facade for all contract types."""
from __future__ import annotations

import importlib

REQUIRED = (
    "LearningStatus",
    "EpisodeOutcome",
    "EpisodeLifecycle",
    "RootCauseCandidate",
    "DriftKind",
    "FailureType",
    "DriftState",
    "CounterfactualAction",
    "SignalEpisode",
    "AttributionReport",
    "FailureRecord",
    "Hypothesis",
    "CounterfactualScenario",
    "CounterfactualReport",
    "ExperimentSpec",
    "MetaDecision",
    "HealthReport",
    "DriftAlert",
    "IntegrityResult",
)


def test_contracts_facade_exports_all_public_symbols():
    mod = importlib.import_module("src.python.learning.contracts")
    missing = [name for name in REQUIRED if not hasattr(mod, name)]
    assert not missing, f"contracts facade missing: {missing}"


def test_contracts_facade_symbols_constructible():
    from src.python.learning.contracts import (
        SignalEpisode,
        AttributionReport,
        FailureRecord,
        Hypothesis,
        ExperimentSpec,
        MetaDecision,
        HealthReport,
        DriftAlert,
        IntegrityResult,
        CounterfactualScenario,
        CounterfactualReport,
        LearningStatus,
    )

    ep = SignalEpisode(
        episode_id="e1", trading_date="2026-09-19", symbol="BBCA", strategy_id="rule_sma20",
    )
    assert ep.symbol == "BBCA"
    ar = AttributionReport(
        episode_id="e1", symbol="BBCA", outcome="LOSS", r_multiple=-1.0,
        primary_strategy="rule_sma20", regime="SIDEWAYS",
    )
    assert ar.pnl == 0.0
    fr = FailureRecord(
        failure_id="f1", episode_id="e1", regime="SIDEWAYS", strategy_id="rule_sma20",
        signal="BUY", r_multiple=-1.0, root_cause="BAD_REGIME",
    )
    assert fr.status == LearningStatus.OBSERVED.value
    h = Hypothesis(hypothesis_id="H1", statement="test")
    assert h.status == LearningStatus.HYPOTHESIS.value
    exp = ExperimentSpec(experiment_id="EXP1", hypothesis_id="H1", name="t")
    assert exp.baseline_id
    md = MetaDecision(symbol="BBCA")
    assert md.recommended_action == "HOLD"
    hr = HealthReport()
    assert hr.data_health == "OK"
    da = DriftAlert(kind="PERFORMANCE", name="p", score=0.1, threshold=0.2, status="OK")
    assert da.status == "OK"
    ir = IntegrityResult(ok=True)
    assert ir.learning_data_integrity == "PASS"
    sc = CounterfactualScenario(name="HOLD", description="x", hypothetical_r=0.0, delta_r=1.0)
    cr = CounterfactualReport(episode_id="e1", actual_r=-1.0, scenarios=[sc])
    assert cr.to_dict()["scenarios"][0]["name"] == "HOLD"


def test_learning_package_imports_via_facade():
    """Import chain: contracts → attribution → failure → loop must resolve."""
    from src.python.learning import (
        SignalEpisode,
        AttributionReport,
        FailureRecord,
        Hypothesis,
        LearningLoop,
        attribute_episode,
        IntegrityResult,
    )
    assert SignalEpisode and AttributionReport and FailureRecord and Hypothesis
    assert LearningLoop and attribute_episode and IntegrityResult
