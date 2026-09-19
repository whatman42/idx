"""Production control plane + Feature SSOT ops signal + cost model split."""
from __future__ import annotations

import pandas as pd
import numpy as np

from src.python.strategy.production_control import (
    assert_production_allowed,
    control_plane_summary,
    eligibility,
    production_strategy_ids,
    shadow_strategy_ids,
)
from src.python.data.costs import (
    CostModel,
    IDXBrokerCostModel,
    SimulationCostModel,
    cost_models_summary,
    default_paper_cost,
)


def test_rule_sma20_is_promoted_only_production():
    ids = production_strategy_ids()
    assert "rule_sma20" in ids
    assert eligibility("rule_sma20").production_allowed is True
    assert eligibility("trend_multi").production_allowed is False
    assert eligibility("trend_multi").shadow_allowed is True


def test_assert_blocks_research():
    try:
        assert_production_allowed("trend_multi")
        assert False, "should have raised"
    except RuntimeError as e:
        assert "production_blocked" in str(e)


def test_control_plane_summary():
    s = control_plane_summary()
    assert s["version"] == "production_control_v2"
    assert "rule_sma20" in s["production"]


def test_cost_model_split():
    sim = default_paper_cost()
    assert isinstance(sim, SimulationCostModel)
    assert sim.model_kind == "SIMULATION"
    brk = IDXBrokerCostModel()
    assert brk.model_kind == "IDX_BROKER"
    assert brk.calibrated is False
    summary = cost_models_summary()
    assert summary["version"] == "cost_model_v2"
    c = CostModel()
    assert c.fee(1_000_000) > 0


def test_production_signal_feature_ssot():
    from src.python.ops.production_signal import production_signals_from_bars

    rng = np.random.default_rng(42)
    rows = []
    for sym in ("BBCA", "BBRI"):
        px = 5000.0
        for i in range(40):
            px = px * (1.0 + float(rng.normal(0.001, 0.015)))
            rows.append({
                "timestamp": pd.Timestamp("2026-01-01") + pd.Timedelta(days=i),
                "symbol": sym,
                "open": px * 0.99,
                "high": px * 1.01,
                "low": px * 0.98,
                "close": px,
                "volume": float(rng.integers(1_000_000, 5_000_000)),
            })
    bars = pd.DataFrame(rows)
    pack = production_signals_from_bars(bars, strategy_id="rule_sma20", include_shadow=True)
    assert pack["path"] == "FEATURE_SSOT"
    assert pack["feature_meta"]["ok"] is True
    assert "rule_sma20" in pack["control_plane"]["production"]
    assert pack["production_all"] is not None
