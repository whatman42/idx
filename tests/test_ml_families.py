from src.python.governor.governor import MLGovernor, ResourceProfile
from src.python.ml.families import ModelFamily, TRAINABLE_FAMILIES
from src.python.ml.features import build_feature_frame, FEATURE_COLS
from src.python.ml.pipeline import run_lightweight_training
from src.python.market.providers import SyntheticProvider

def test_three_distinct_families():
    vals = [f.value for f in TRAINABLE_FAMILIES]
    assert len(vals) == len(set(vals)) == 3
    assert ModelFamily.LGBM_BOOST in TRAINABLE_FAMILIES
    assert ModelFamily.RF_BAG in TRAINABLE_FAMILIES
    assert ModelFamily.LOGREG_LINEAR in TRAINABLE_FAMILIES

def test_governor_never_duplicates_family():
    gov = MLGovernor(resources=ResourceProfile(training_budget_sec=1200))
    plan = gov.training_plan(1200)
    fams = plan["families"]
    assert len(fams) == len(set(fams))
    assert len(fams) == 3

def test_governor_low_budget_linear_only():
    gov = MLGovernor()
    plan = gov.training_plan(50)
    assert plan["allow_train"] is True
    assert plan["families"] == ["LOGREG_LINEAR"]

def test_train_all_families_synthetic(tmp_path):
    bars = SyntheticProvider(n=100, seed=0).fetch(["BBCA", "BBRI", "TLKM", "ASII"]).df
    rep = run_lightweight_training(bars, out_dir=tmp_path, budget_sec=600)
    assert rep["promoted"] is False
    assert rep["production_unchanged"] is True
    families = [r.get("family") for r in rep.get("results") if r.get("status") != "TRAIN_FAILED"]
    assert len(families) == len(set(families))
    assert len(families) >= 1

def test_features_causal_columns():
    bars = SyntheticProvider(n=80, seed=1).fetch(["BBCA"]).df
    feat = build_feature_frame(bars)
    for c in FEATURE_COLS:
        assert c in feat.columns
