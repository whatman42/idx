"""Governor utility selection + shadow challenger isolation tests."""
from __future__ import annotations
import pandas as pd
from src.python.governor.governor import MLGovernor, SafetyContext, MarketContext
from src.python.governor.utility import score_model_utility, WEIGHTS
from src.python.ml.families import ModelFamily, TRAINABLE_FAMILIES
from src.python.shadow.compare import run_shadow_evaluation, PRODUCTION_MODEL
from src.python.shadow.ledger import load_governor_memory, save_governor_memory
from src.python.market.providers import SyntheticProvider
from src.python.ops.paper_portfolio import paper_reset_scope, PaperPortfolioStore, new_session


def test_utility_weights_sum_to_one():
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9


def test_utility_unknown_without_evidence():
    u = score_model_utility(model_id="x", family="LOGREG_LINEAR", metrics={})
    assert u.status == "UTILITY_UNKNOWN"
    assert u.score == 0.0


def test_utility_scored_with_metrics():
    u = score_model_utility(
        model_id="idx_logreg_lw",
        family="LOGREG_LINEAR",
        metrics={
            "expectancy": 0.05,
            "profit_factor": 1.2,
            "max_drawdown": 0.1,
            "positive_windows": 3,
            "total_windows": 5,
            "cost_survive_ratio": 0.5,
            "train_sec": 10,
        },
    )
    assert u.status in ("UTILITY_SCORED", "UTILITY_PARTIAL")
    assert 0.0 < u.score <= 1.0


def test_governor_safety_blocks_all():
    g = MLGovernor()
    sel = g.select_models(remaining_sec=500, safety=SafetyContext(dq_ok=False))
    assert sel["allow"] is False
    assert sel["families"] == []
    assert sel["safety_precedence"] is True


def test_governor_budget_skip():
    g = MLGovernor()
    sel = g.select_models(remaining_sec=10, safety=SafetyContext())
    assert sel["allow"] is False
    assert sel["workload"] == "SKIP"


def test_governor_one_model_per_family():
    g = MLGovernor()
    sel = g.select_models(remaining_sec=600, safety=SafetyContext())
    fams = sel["families"]
    assert len(fams) == len(set(fams))
    assert set(fams).issubset({f.value for f in TRAINABLE_FAMILIES})


def test_governor_deterministic():
    g = MLGovernor()
    a = g.select_models(remaining_sec=200, safety=SafetyContext(), market=MarketContext(drift_score=0.2))
    b = g.select_models(remaining_sec=200, safety=SafetyContext(), market=MarketContext(drift_score=0.2))
    assert a["families"] == b["families"]
    assert a["model_ids"] == b["model_ids"]


def test_governor_prefer_simple_under_high_drift():
    g = MLGovernor()
    sel = g.select_models(
        remaining_sec=80,
        safety=SafetyContext(),
        market=MarketContext(drift_score=0.9, regime_vol=2.0),
    )
    assert sel["allow"] is True
    assert "LOGREG_LINEAR" in sel["families"]


def test_shadow_does_not_change_production_pointer(tmp_path):
    bars = SyntheticProvider(n=100, seed=7).fetch(["BBCA", "BBRI", "TLKM", "ASII"]).df
    rows = []
    for sym, g in bars.groupby("symbol"):
        g = g.sort_values("timestamp")
        last = g.iloc[-1]
        rows.append({"timestamp": last["timestamp"], "symbol": sym, "side": 1, "confidence": 0.55})
    prod = pd.DataFrame(rows)
    state = tmp_path / "ops"
    state.mkdir()
    pf_path = state / "paper_portfolio.json"
    store = PaperPortfolioStore(pf_path)
    pf = new_session(model_version=PRODUCTION_MODEL)
    store.save_atomic(pf)
    before = pf_path.read_text()
    rep = run_shadow_evaluation(bars, prod, state_dir=str(state), budget_sec=120)
    after = pf_path.read_text()
    assert before == after
    assert rep["production_pointer_unchanged"] is True
    assert rep["promoted"] is False
    assert rep["production_model"] == PRODUCTION_MODEL
    assert (state / "shadow" / "last_shadow_report.json").exists()


def test_shadow_disagreement_structure(tmp_path):
    bars = SyntheticProvider(n=90, seed=3).fetch(["BBCA", "BBRI", "TLKM"]).df
    prod = pd.DataFrame([
        {"timestamp": bars["timestamp"].max(), "symbol": "BBCA", "side": 1, "confidence": 0.5},
        {"timestamp": bars["timestamp"].max(), "symbol": "BBRI", "side": 0, "confidence": 0.5},
    ])
    rep = run_shadow_evaluation(bars, prod, state_dir=str(tmp_path), budget_sec=120)
    assert rep["status"] in ("SHADOW_OK", "SHADOW_SKIPPED")
    if rep["status"] == "SHADOW_OK":
        for mid, ch in rep["challengers"].items():
            assert ch.get("promotion_approved") is False


def test_governor_memory_survives_separate_from_paper_reset(tmp_path):
    d = tmp_path / "ops"
    save_governor_memory(d, {"idx_logreg_lw": {"score": 0.7, "status": "UTILITY_PARTIAL"}})
    mem = load_governor_memory(d)
    assert "idx_logreg_lw" in mem
    scope = paper_reset_scope()
    assert "does_not" in scope or "preserved" in scope


def test_families_still_exactly_three():
    assert len(TRAINABLE_FAMILIES) == 3
    assert ModelFamily.LOGREG_LINEAR in TRAINABLE_FAMILIES
    assert ModelFamily.RF_BAG in TRAINABLE_FAMILIES
    assert ModelFamily.LGBM_BOOST in TRAINABLE_FAMILIES
