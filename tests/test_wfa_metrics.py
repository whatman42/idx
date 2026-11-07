"""Unit tests for research WFA metrics — no network, no ledger mutation."""
from __future__ import annotations

from src.python.research.wfa_metrics import (
    buy_hold_total_return,
    classify_decay,
    cost_sensitivity_summary,
    decay_ratio,
    enrich_oos_research_metrics,
    strategy_vs_buyhold,
    train_oos_degradation,
)
from src.python.research.experiment_versions import (
    assert_not_production,
    get_experiment,
    list_experiments,
)


def test_decay_ratio_basic():
    assert decay_ratio(0.7, 1.0) == 0.7
    assert classify_decay(0.75) == "STRONG"
    assert classify_decay(0.55) == "ACCEPTABLE"
    assert classify_decay(0.4) == "WEAK"
    assert classify_decay(0.1) == "POOR"
    assert decay_ratio(1.0, 0.0) is None
    assert decay_ratio(None, 1.0) is None


def test_train_oos_degradation_matches_evaluator_shape():
    d = train_oos_degradation(1.0, 0.4)
    assert d is not None and abs(d - 0.6) < 1e-9


def test_buy_hold_and_benchmark():
    r = buy_hold_total_return([100.0, 110.0])
    assert r is not None and abs(r - 0.1) < 1e-9
    bh = strategy_vs_buyhold(0.12, 0.10)
    assert bh["beats_buyhold"] is True
    assert abs(bh["excess_vs_buyhold"] - 0.02) < 1e-9


def test_enrich_bundle():
    m = enrich_oos_research_metrics(
        is_expectancy=1.0,
        oos_expectancy=0.6,
        strategy_total_return=0.05,
        buyhold_total_return=0.08,
    )
    assert m["decay_class"] == "ACCEPTABLE"
    assert m["auto_promote"] is False
    assert m["plane"] == "RESEARCH_ONLY"
    assert m["benchmark"]["beats_buyhold"] is False


def test_cost_sensitivity_paper_stays_simulation():
    s = cost_sensitivity_summary()
    assert s["paper_path_uses"] == "SIMULATION"
    assert "idx_broker_adapter" in s


def test_experiment_registry_not_production():
    rows = list_experiments()
    assert rows
    for r in rows:
        assert r.get("production_eligible") is False
    exp = get_experiment("crypto_sma20_cooldown_v1")
    assert exp is not None
    assert_not_production("crypto_sma20_cooldown_v1")
