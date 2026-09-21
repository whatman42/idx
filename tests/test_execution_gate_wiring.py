"""Integration: paper execution paths require market structure gate."""
from __future__ import annotations

from src.python.market_structure import (
    ExecutionGate,
    InstrumentEligibility,
    MarketStructure,
    MarketStructureProvider,
    MarketStructureSnapshot,
    OrderRequest,
    PriceRules,
    TradingSession,
)
from src.python.ops.execution_authority import clear_for_execution, default_continuous_provider
from src.python.ops.paper_portfolio import apply_long_entry, new_session


def _gate_for(status: str, symbol: str = "ABC") -> ExecutionGate:
    return ExecutionGate(
        provider=MarketStructureProvider.from_status_map({symbol: status}),
        price_rules={symbol: PriceRules(symbol=symbol, tick_size=5.0, lot_size=100, ara=2000.0, arb=100.0)},
        require_price_rules=True,
    )


def test_signal_to_execution_requires_market_gate():
    state = new_session(initial_capital=10_000_000.0)
    _, tr, cls = apply_long_entry(
        state, symbol="ABC", price=1000.0, weight=0.05, signal_id="s1",
        timestamp="2026-09-21T10:00:00+00:00", enforce_market_gate=True, market_gate=None,
    )
    assert tr is None and cls == "SKIPPED_MS_MISSING_GATE"


def test_fca_signal_cannot_create_fill():
    state = new_session(initial_capital=10_000_000.0)
    _, tr, cls = apply_long_entry(
        state, symbol="ABC", price=1000.0, weight=0.05, signal_id="s1",
        timestamp="2026-09-21T10:00:00+00:00", market_gate=_gate_for("FCA"), enforce_market_gate=True,
    )
    assert tr is None and "SKIPPED_MS" in cls


def test_halted_signal_cannot_create_fill():
    state = new_session(initial_capital=10_000_000.0)
    _, tr, cls = apply_long_entry(
        state, symbol="ABC", price=1000.0, weight=0.05, signal_id="s1",
        timestamp="2026-09-21T10:00:00+00:00", market_gate=_gate_for("HALTED"), enforce_market_gate=True,
    )
    assert tr is None and "SKIPPED_MS" in cls


def test_unknown_status_cannot_create_fill():
    state = new_session(initial_capital=10_000_000.0)
    gate = ExecutionGate(provider=MarketStructureProvider({}), require_price_rules=False)
    _, tr, cls = apply_long_entry(
        state, symbol="ABC", price=1000.0, weight=0.05, signal_id="s1",
        timestamp="2026-09-21T10:00:00+00:00", market_gate=gate, enforce_market_gate=True,
    )
    assert tr is None


def test_invalid_tick_cannot_create_fill():
    vo, res = clear_for_execution(_gate_for("CONTINUOUS"), OrderRequest("ABC", 1, 1003.0, 100))
    assert vo is None and res.reason.value == "PRICE_NOT_ON_TICK"


def test_ara_violation_cannot_create_fill():
    gate = _gate_for("CONTINUOUS")
    gate.price_rules = {"ABC": PriceRules(symbol="ABC", tick_size=5.0, lot_size=100, ara=900.0, arb=100.0)}
    vo, res = clear_for_execution(gate, OrderRequest("ABC", 1, 1000.0, 100))
    assert vo is None and res.reason.value == "PRICE_ABOVE_AR_LIMIT"


def test_invalid_lot_cannot_create_fill():
    vo, res = clear_for_execution(_gate_for("CONTINUOUS"), OrderRequest("ABC", 1, 1000.0, 50))
    assert vo is None and res.reason.value == "INVALID_LOT"


def test_recheck_blocks_after_market_state_change():
    prov = MarketStructureProvider.from_status_map({"ABC": "CONTINUOUS"})
    gate = ExecutionGate(
        provider=prov,
        price_rules={"ABC": PriceRules(symbol="ABC", tick_size=5.0, lot_size=100, ara=5000.0, arb=1.0)},
    )
    prior = gate.allow_order_intent("ABC")
    prov.upsert(
        MarketStructureSnapshot(
            symbol="ABC",
            structure=MarketStructure.FCA,
            as_of=prior.detected_at,
            source="test",
            session=TradingSession.UNKNOWN,
            eligibility=InstrumentEligibility.FCA,
        )
    )
    vo, res = clear_for_execution(gate, OrderRequest("ABC", 1, 1000.0, 100), prior=prior)
    assert vo is None


def test_gate_failure_produces_no_ledger_mutation():
    state = new_session(initial_capital=5_000_000.0)
    cash0 = state.cash
    apply_long_entry(
        state, symbol="ABC", price=1000.0, weight=0.05, signal_id="s1",
        timestamp="2026-09-21T10:00:00+00:00", market_gate=_gate_for("FCA"), enforce_market_gate=True,
    )
    assert state.cash == cash0 and len(state.open_positions()) == 0


def test_provider_default_not_continuous_for_unknown_symbol():
    prov = default_continuous_provider(["BBCA"])
    assert prov.get("BBCA").structure.value == "CONTINUOUS"
    assert prov.get("UNKNOWNX").structure.value == "UNKNOWN"
