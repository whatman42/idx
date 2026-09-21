"""Market structure & execution safety — FCA, session, ARA/ARB, tick/lot."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.python.market_structure import (
    BlockReason,
    ExecutionGate,
    InstrumentEligibility,
    MarketStructure,
    MarketStructureProvider,
    MarketStructureSnapshot,
    OrderRequest,
    PriceRules,
    TradingSession,
    evaluate_structure,
    gemini_cannot_override,
    validate_order,
)


def _snap(
    sym: str,
    structure: MarketStructure,
    *,
    hours_ago: float = 0.0,
    source: str = "test",
    session: TradingSession = TradingSession.OPEN,
    eligibility: InstrumentEligibility = InstrumentEligibility.TRADEABLE,
) -> MarketStructureSnapshot:
    as_of = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return MarketStructureSnapshot(
        symbol=sym,
        structure=structure,
        as_of=as_of,
        source=source,
        version="t1",
        session=session,
        eligibility=eligibility,
    )


def test_normal_stock_passes_fca_gate():
    assert evaluate_structure(_snap("BBCA", MarketStructure.CONTINUOUS)).allow is True


def test_fca_stock_blocked():
    r = evaluate_structure(_snap("ABCD", MarketStructure.FCA, eligibility=InstrumentEligibility.FCA))
    assert r.allow is False and r.reason == BlockReason.FCA_INSTRUMENT


def test_unknown_market_structure_blocked():
    r = evaluate_structure(_snap("ZZZZ", MarketStructure.UNKNOWN, eligibility=InstrumentEligibility.UNKNOWN))
    assert r.allow is False


def test_stale_market_structure_blocked():
    r = evaluate_structure(_snap("BBCA", MarketStructure.CONTINUOUS, hours_ago=48), max_age_seconds=86_400)
    assert r.reason == BlockReason.MARKET_DATA_STALE


def test_halted_stock_blocked():
    r = evaluate_structure(_snap("HALT", MarketStructure.HALTED, eligibility=InstrumentEligibility.HALTED))
    assert r.reason in (BlockReason.TRADING_HALT, BlockReason.HALTED)


def test_pre_open_session_blocked():
    r = evaluate_structure(_snap("BBCA", MarketStructure.CONTINUOUS, session=TradingSession.PRE_OPEN))
    assert r.allow is False and r.reason == BlockReason.SESSION_NOT_CONTINUOUS


def test_price_above_ara_blocked():
    rules = PriceRules(symbol="ABC", tick_size=5.0, lot_size=100, ara=1240.0, arb=1000.0)
    ok, reason, _ = validate_order(OrderRequest("ABC", 1, 1250.0, 100), rules)
    assert ok is False and reason == BlockReason.PRICE_ABOVE_AR_LIMIT


def test_price_below_arb_blocked():
    rules = PriceRules(symbol="ABC", tick_size=5.0, lot_size=100, ara=1300.0, arb=1100.0)
    ok, reason, _ = validate_order(OrderRequest("ABC", 1, 1000.0, 100), rules)
    assert ok is False and reason == BlockReason.PRICE_BELOW_AR_LIMIT


def test_price_not_on_tick_blocked():
    rules = PriceRules(symbol="ABC", tick_size=5.0, lot_size=100, ara=2000.0, arb=100.0)
    ok, reason, _ = validate_order(OrderRequest("ABC", 1, 1257.0, 100), rules)
    assert ok is False and reason == BlockReason.PRICE_NOT_ON_TICK


def test_invalid_lot_blocked():
    rules = PriceRules(symbol="ABC", tick_size=5.0, lot_size=100, ara=2000.0, arb=100.0)
    ok, reason, _ = validate_order(OrderRequest("ABC", 1, 1250.0, 50), rules)
    assert ok is False and reason == BlockReason.INVALID_LOT


def test_execution_gate_full_order_pass():
    prov = MarketStructureProvider.from_status_map({"BBCA": "CONTINUOUS"})
    rules = {"BBCA": PriceRules(symbol="BBCA", tick_size=25.0, lot_size=100, ara=10000.0, arb=100.0)}
    gate = ExecutionGate(provider=prov, price_rules=rules)
    assert gate.validate_order_request(OrderRequest("BBCA", 1, 8750.0, 100)).allow is True


def test_fca_signal_never_reaches_broker():
    broker_log = []
    gate = ExecutionGate(provider=MarketStructureProvider.from_status_map({"ABC": "FCA"}), require_price_rules=False)
    r = gate.allow_order_intent("ABC")
    if r.allow:
        broker_log.append("SENT")
    assert r.allow is False and broker_log == []


def test_gemini_cannot_override_fca_gate():
    blocked = evaluate_structure(_snap("ABC", MarketStructure.FCA, eligibility=InstrumentEligibility.FCA))
    assert gemini_cannot_override(blocked, True).allow is False


def test_provider_miss_is_unknown_not_continuous():
    assert evaluate_structure(MarketStructureProvider({}).get("NOSYM")).allow is False
