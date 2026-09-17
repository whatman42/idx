"""Institutional risk gate — 1% risk sizing, heat, DD halt, max positions."""
from src.python.ops.risk_gate import (
    MAX_OPEN_POSITIONS,
    MAX_PORTFOLIO_HEAT,
    RISK_PER_TRADE,
    estimate_open_heat,
    gate_new_entry,
    risk_defaults,
)


def test_risk_defaults_version():
    d = risk_defaults()
    assert d["version"] == "risk_gate_v1"
    assert abs(d["risk_per_trade"] - 0.01) < 1e-12


def test_size_scales_inverse_to_stop():
    g_tight = gate_new_entry(
        equity=10_000_000, cash=10_000_000, open_positions={},
        current_drawdown=0.0, stop_distance_pct=0.02,
    )
    g_wide = gate_new_entry(
        equity=10_000_000, cash=10_000_000, open_positions={},
        current_drawdown=0.0, stop_distance_pct=0.15,
    )
    assert g_tight.allow_entry and g_wide.allow_entry
    assert g_tight.weight > g_wide.weight
    assert g_tight.weight <= 0.12 + 1e-9
    assert abs(g_wide.weight - min(RISK_PER_TRADE / 0.15, 0.12)) < 1e-6 or g_wide.weight <= 0.12


def test_halt_on_drawdown():
    g = gate_new_entry(
        equity=8_000_000, cash=8_000_000, open_positions={},
        current_drawdown=0.21, stop_distance_pct=0.03,
    )
    assert not g.allow_entry
    assert g.reason == "HALT_DRAWDOWN"


def test_max_open_positions():
    pos = {f"S{i}": {"qty": 100, "avg_entry": 1000, "sl": 970} for i in range(MAX_OPEN_POSITIONS)}
    g = gate_new_entry(
        equity=10_000_000, cash=5_000_000, open_positions=pos,
        current_drawdown=0.0, stop_distance_pct=0.03,
    )
    assert not g.allow_entry
    assert g.reason == "MAX_OPEN_POSITIONS"


def test_heat_blocks():
    equity = 10_000_000.0
    pos = {"HOT": {"qty": 5000, "avg_entry": 1000, "sl": 880}}
    heat = estimate_open_heat(pos, equity=equity)
    assert heat >= MAX_PORTFOLIO_HEAT - 1e-6
    g = gate_new_entry(
        equity=equity, cash=5_000_000, open_positions=pos,
        current_drawdown=0.0, stop_distance_pct=0.03,
    )
    assert not g.allow_entry
    assert g.reason == "PORTFOLIO_HEAT_FULL"


def test_dd_warn_halves_size():
    g0 = gate_new_entry(
        equity=10_000_000, cash=10_000_000, open_positions={},
        current_drawdown=0.0, stop_distance_pct=0.05,
    )
    g1 = gate_new_entry(
        equity=10_000_000, cash=10_000_000, open_positions={},
        current_drawdown=0.16, stop_distance_pct=0.05,
    )
    assert g0.allow_entry and g1.allow_entry
    assert g1.weight < g0.weight
    assert "dd_warn_half_size" in g1.caps
