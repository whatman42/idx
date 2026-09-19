"""Learning loop: attribution, failure memory, hypothesis, meta, drift, promotion boundary."""
from __future__ import annotations

from src.python.learning import (
    FailureMemory,
    KnowledgeBase,
    LearningLoop,
    MetaLearner,
    SignalEpisode,
    attribute_episode,
    analyze_counterfactuals,
    diagnose,
    drift_from_episodes,
    generate_hypotheses_from_failures,
)
from src.python.learning.experiment import ExperimentLedger, build_experiment_from_hypothesis


def _ep(**kw) -> SignalEpisode:
    base = dict(
        episode_id="EP1",
        trading_date="2026-09-19",
        symbol="BBCA",
        strategy_id="momentum_v2",
        strategy_version="1.0",
        regime="SIDEWAYS",
        side=1,
        confidence=0.5,
        score=0.02,
        ensemble_votes={"momentum_v2": 0.4, "rule_sma20": -0.1},
        feature_snapshot={"mom_10_21": 0.01, "vol_z_20": 1.5},
        risk_decision="ALLOW",
        governor_decision="BUY",
        entry_px=100.0,
        exit_px=98.2,
        exit_reason="SL",
        r_multiple=-1.82,
        pnl=-182.0,
        outcome="LOSS",
    )
    base.update(kw)
    return SignalEpisode(**base)


def test_attribution_loss_sideways():
    a = attribute_episode(_ep())
    assert a.outcome == "LOSS"
    assert a.primary_strategy == "momentum_v2"
    assert any("REGIME" in c or "FALSE" in c or "ENSEMBLE" in c or "STOP" in c for c in a.root_cause_candidates)


def test_counterfactual_has_hold_and_regime_block():
    cf = analyze_counterfactuals(_ep())
    names = {s.name for s in cf.scenarios}
    assert "HOLD" in names
    assert "REGIME_BLOCK" in names
    assert cf.actual_r < 0


def test_failure_memory_observed_not_auto_promoted():
    mem = FailureMemory()
    rec = mem.observe(_ep(), failure_id="F1")
    assert rec is not None
    assert rec.status == "OBSERVED"
    assert "penalty" in rec.proposed_action or "monitor" in rec.proposed_action


def test_hypothesis_from_failures():
    mem = FailureMemory()
    for i in range(5):
        mem.observe(_ep(episode_id=f"E{i}", r_multiple=-1.5), failure_id=f"F{i}")
    hyps = generate_hypotheses_from_failures(mem.list_observed(), min_similar=1)
    assert len(hyps) >= 1
    assert hyps[0].status == "HYPOTHESIS"
    assert hyps[0].counter_hypothesis


def test_meta_learner_advisory_not_fill():
    ml = MetaLearner()
    for i in range(10):
        ml.observe(_ep(episode_id=f"W{i}", r_multiple=0.5 if i % 2 == 0 else -0.5, outcome="WIN" if i % 2 == 0 else "LOSS", regime="bull"))
    d = ml.decide(symbol="BBCA", strategy_scores={"momentum_v2": 0.3}, regime="bull")
    assert d.uncertainty >= 0
    assert d.recommended_action in ("BUY", "HOLD", "NO_SIGNAL")
    assert "expected_edge" in d.to_dict()


def test_drift_and_health():
    hist = [_ep(episode_id=f"H{i}", r_multiple=0.5, outcome="WIN", regime="bull") for i in range(30)]
    recent = [_ep(episode_id=f"R{i}", r_multiple=-0.8, outcome="LOSS", regime="SIDEWAYS") for i in range(20)]
    alerts = drift_from_episodes(hist, recent)
    assert any(a.kind == "PERFORMANCE" for a in alerts)
    health = diagnose(episodes=hist + recent, drift_alerts=alerts)
    assert health.decision_confidence in ("OK", "INSUFFICIENT_EVIDENCE", "BLOCKED", "WARN")


def test_learning_loop_never_auto_promotes():
    loop = LearningLoop()
    for i in range(5):
        loop.observe_episode(_ep(episode_id=f"L{i}", r_multiple=-1.2))
    result = loop.run_learning_cycle(experiment_evidence={
        "signal_defined": True,
        "feature_ssot": True,
        "lookahead_safe": True,
        "data_quality_ok": True,
        "out_of_sample": {"evaluated": False, "n_trades": 0},
    })
    assert result["principle"] == "hypothesis_ok_production_requires_promotion_gate"
    for c in result["experiment_candidacy"]:
        assert c["approved"] is False


def test_experiment_ledger_immutable():
    led = ExperimentLedger()
    from src.python.learning.contracts import Hypothesis
    h = Hypothesis(hypothesis_id="HYP-1", statement="test", strategies=["momentum_v2"])
    spec = build_experiment_from_hypothesis(
        h, experiment_id="EXP-1", name="test_exp",
        challenger_strategy_id="momentum_v2", challenger_version="1.1",
    )
    led.register(spec)
    try:
        led.register(spec)
        assert False, "should reject duplicate"
    except RuntimeError as e:
        assert "immutable" in str(e)


def test_knowledge_base_remembers_hypothesis():
    kb = KnowledgeBase()
    from src.python.learning.contracts import Hypothesis
    h = Hypothesis(hypothesis_id="HYP-00421", statement="volume-confirmed breakout reduces false entries",
                   regimes=["SIDEWAYS"], status="CANDIDATE", evidence_count=143)
    kb.upsert_hypothesis(h)
    found = kb.already_tried("volume-confirmed")
    assert len(found) == 1
    assert found[0]["hypothesis_id"] == "HYP-00421"
