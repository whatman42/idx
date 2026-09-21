"""FCA / market-structure hard gate — Policy A fail-closed."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.python.market_structure import (
    BlockReason,
    ExecutionGate,
    MarketStructure,
    MarketStructureProvider,
    MarketStructureSnapshot,
    evaluate_structure,
    gemini_cannot_override,
)


def _snap(sym: str, structure: MarketStructure, *, hours_ago: float = 0.0, source: str = "test") -> MarketStructureSnapshot:
    as_of = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return MarketStructureSnapshot(symbol=sym, structure=structure, as_of=as_of, source=source, version="t1")


def test_normal_stock_passes_fca_gate():
    r = evaluate_structure(_snap("BBCA", MarketStructure.CONTINUOUS))
    assert r.allow is True
    assert r.reason == BlockReason.NONE


def test_fca_stock_blocked():
    r = evaluate_structure(_snap("ABCD", MarketStructure.FCA))
    assert r.allow is False
    assert r.reason == BlockReason.FCA_INSTRUMENT
    assert r.to_dict()["order_broker"] == "NOT_SENT"


def test_unknown_market_structure_blocked():
    r = evaluate_structure(_snap("ZZZZ", MarketStructure.UNKNOWN))
    assert r.allow is False
    assert r.reason == BlockReason.MARKET_STRUCTURE_UNKNOWN


def test_stale_market_structure_blocked():
    r = evaluate_structure(_snap("BBCA", MarketStructure.CONTINUOUS, hours_ago=48), max_age_seconds=86_400)
    assert r.allow is False
    assert r.reason == BlockReason.MARKET_DATA_STALE


def test_halted_stock_blocked():
    r = evaluate_structure(_snap("HALT", MarketStructure.HALTED))
    assert r.allow is False
    assert r.reason == BlockReason.HALTED


def test_missing_snapshot_blocked():
    r = evaluate_structure(None)
    assert r.allow is False
    assert r.reason == BlockReason.MISSING_SNAPSHOT


def test_fca_status_change_between_signal_and_execution():
    prov = MarketStructureProvider({"ABC": _snap("ABC", MarketStructure.CONTINUOUS)})
    gate = ExecutionGate(provider=prov)
    prior = gate.allow_order_intent("ABC")
    assert prior.allow is True
    prov.upsert(_snap("ABC", MarketStructure.FCA))
    later = gate.recheck_before_execution("ABC", prior=prior)
    assert later.allow is False
    assert later.reason in (BlockReason.STRUCTURE_CHANGED, BlockReason.FCA_INSTRUMENT)


def test_execution_rechecks_fca_status():
    prov = MarketStructureProvider.from_status_map({"XYZ": "CONTINUOUS"})
    gate = ExecutionGate(provider=prov)
    assert gate.recheck_before_execution("XYZ").allow is True


def test_fca_cannot_create_order_intent():
    prov = MarketStructureProvider.from_status_map({"FCA1": "FCA"})
    gate = ExecutionGate(provider=prov)
    r = gate.allow_order_intent("FCA1")
    assert r.allow is False


def test_fca_block_reason_is_auditable():
    r = evaluate_structure(_snap("ABC", MarketStructure.FCA, source="bei_notice"))
    d = r.to_dict()
    assert d["reason"] == "FCA_INSTRUMENT"
    assert d["symbol"] == "ABC"
    assert d["market_mode"] == "FCA"
    assert d["source"] == "bei_notice"


def test_gemini_cannot_override_fca_gate():
    blocked = evaluate_structure(_snap("ABC", MarketStructure.FCA))
    out = gemini_cannot_override(blocked, gemini_says_ok=True)
    assert out.allow is False


def test_fca_signal_never_reaches_broker():
    broker_log: list[str] = []

    def fake_broker_send(order: dict) -> None:
        broker_log.append("SENT")

    prov = MarketStructureProvider.from_status_map({"ABC": "FCA"})
    gate = ExecutionGate(provider=prov)
    r = gate.allow_order_intent("ABC")
    if r.allow:
        fake_broker_send({"symbol": "ABC"})
    assert r.allow is False
    assert broker_log == []
    gate.assert_never_broker()


def test_provider_miss_is_unknown_not_continuous():
    prov = MarketStructureProvider({})
    snap = prov.get("NOSYM")
    assert snap.structure == MarketStructure.UNKNOWN
    r = evaluate_structure(snap)
    assert r.allow is False
