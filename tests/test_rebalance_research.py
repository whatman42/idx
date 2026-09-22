"""Rebalance research plane — no execution, equal-weight + relative drift + trim-only."""
from __future__ import annotations

from src.python.research.rebalance import (
    DEFAULT_RELATIVE_DRIFT_THRESHOLD,
    RebalanceActionKind,
    build_rebalance_plan,
    calculate_target_weights,
    plan_from_portfolio_snapshot,
    relative_drift,
)


def test_equal_weight_two_positions():
    tw = calculate_target_weights(["ABDA", "AGAR"])
    assert tw["ABDA"] == 0.5 and tw["AGAR"] == 0.5


def test_relative_drift_formula():
    assert abs(relative_drift(0.12, 0.10) - 0.20) < 1e-12


def test_no_rebalance_single_position():
    plan = build_rebalance_plan(market_values={"ABDA": 1_000_000}, equity=10_000_000)
    assert plan.n_open == 1
    assert plan.trigger_count == 0
    assert any("n_open" in n for n in plan.notes)


def test_balanced_two_positions_no_trigger():
    plan = build_rebalance_plan(
        market_values={"ABDA": 1_000_000, "AGAR": 1_150_000},
        equity=9_995_698,
        threshold=0.20,
    )
    assert plan.n_open == 2
    assert plan.trigger_count == 0
    assert all(leg.kind != RebalanceActionKind.TRIM_CANDIDATE for leg in plan.legs)
    assert plan.live_execution is False and plan.broker_execution is False


def test_overweight_triggers_trim_candidate_only():
    plan = build_rebalance_plan(
        market_values={"AAA": 6_100_000, "BBB": 1_000_000},
        equity=10_000_000,
        threshold=0.20,
    )
    trims = [leg for leg in plan.legs if leg.kind == RebalanceActionKind.TRIM_CANDIDATE]
    assert plan.trigger_count >= 1
    assert any(leg.symbol == "AAA" for leg in trims)
    ups = [leg for leg in plan.legs if leg.kind == RebalanceActionKind.TOP_UP_FORBIDDEN]
    assert any(leg.symbol == "BBB" for leg in ups)
    assert plan.plane == "RESEARCH_SHADOW"
    assert plan.to_dict()["execution_authority"] == "NONE_RESEARCH_ONLY"


def test_plan_never_executable_flags():
    plan = build_rebalance_plan(market_values={"A": 100, "B": 100}, equity=1000)
    d = plan.to_dict()
    assert d["live_execution"] is False
    assert d["broker_execution"] is False
    assert "market_structure_gate" in d["requires_for_future_exec"]


def test_plan_from_portfolio_snapshot():
    plan = plan_from_portfolio_snapshot(
        open_positions={
            "X": {"qty": 100, "last_mark": 50.0},
            "Y": {"qty": 100, "last_mark": 50.0},
        },
        equity=20_000,
        threshold=DEFAULT_RELATIVE_DRIFT_THRESHOLD,
    )
    assert plan.n_open == 2
    assert plan.trigger_count == 0


def test_no_apply_exit_import_side_effect():
    import ast
    import src.python.research.rebalance as m

    tree = ast.parse(open(m.__file__).read())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    joined = " ".join(imports)
    assert "paper_portfolio" not in joined
    assert "signal_bot" not in joined
    assert "execution_authority" not in joined
