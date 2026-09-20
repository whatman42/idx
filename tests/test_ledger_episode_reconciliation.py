"""Adversarial ledger ↔ episode ↔ attribution reconciliation."""
from __future__ import annotations

from src.python.learning.contracts import SignalEpisode
from src.python.learning.integrity import (
    LedgerTradeFact,
    gate_learning_on_integrity,
    reconcile_episode_fields,
    reconcile_episode_pnl,
)


def _ep(**kw) -> SignalEpisode:
    base = dict(
        episode_id="E1", trading_date="2026-09-19", symbol="BBCA",
        strategy_id="rule_sma20", side=1, entry_px=100.0, exit_px=101.0,
        qty=10.0, fees=1.5, pnl=8.5, outcome="WIN", lifecycle="COMPLETED",
        fill_id="F1", signal_id="S1", idempotency_key="K1",
    )
    base.update(kw)
    return SignalEpisode(**base)


def test_pnl_match_pass():
    ep = _ep()
    facts = [LedgerTradeFact(episode_id="E1", signal_id="S1", symbol="BBCA",
                             entry_price=100.0, exit_price=101.0, quantity=10.0,
                             fees=1.5, realized_pnl=8.5, trade_id="F1")]
    r = reconcile_episode_fields([ep], facts)
    assert r.ok
    assert r.learning_data_integrity == "PASS"
    g = gate_learning_on_integrity(r)
    assert g["research"] == "ALLOW"


def test_pnl_mismatch_blocks():
    ep = _ep(pnl=8.5)
    facts = [LedgerTradeFact(episode_id="E1", realized_pnl=99.0, trade_id="F1")]
    r = reconcile_episode_fields([ep], facts)
    assert not r.ok
    assert any("pnl_mismatch" in i for i in r.issues)
    g = gate_learning_on_integrity(r)
    assert g["research"] == "BLOCKED"
    assert g["evidence"] == "INVALID"
    assert g["promotion_candidacy"] == "BLOCKED"


def test_fee_mismatch():
    ep = _ep(fees=1.5)
    facts = [LedgerTradeFact(episode_id="E1", fees=9.0, realized_pnl=8.5, trade_id="F1")]
    r = reconcile_episode_fields([ep], facts)
    assert not r.ok
    assert any("fee_mismatch" in i for i in r.issues)


def test_entry_exit_qty_mismatch():
    ep = _ep()
    facts = [LedgerTradeFact(episode_id="E1", entry_price=50.0, exit_price=200.0,
                             quantity=1.0, realized_pnl=8.5, trade_id="F1")]
    r = reconcile_episode_fields([ep], facts)
    assert not r.ok
    assert any("entry_mismatch" in i for i in r.issues)
    assert any("exit_mismatch" in i for i in r.issues)
    assert any("quantity_mismatch" in i for i in r.issues)


def test_signal_identity_mismatch():
    ep = _ep(signal_id="S1")
    facts = [LedgerTradeFact(episode_id="E1", signal_id="OTHER", realized_pnl=8.5, trade_id="F1")]
    r = reconcile_episode_fields([ep], facts)
    assert any("signal_identity_mismatch" in i for i in r.issues)


def test_timestamp_mismatch():
    ep = _ep(meta={"entry_timestamp": "2026-01-01T00:00:00Z"})
    facts = [LedgerTradeFact(episode_id="E1", entry_timestamp="2026-01-02T00:00:00Z",
                             realized_pnl=8.5, trade_id="F1")]
    r = reconcile_episode_fields([ep], facts)
    assert any("timestamp_mismatch" in i for i in r.issues)


def test_duplicate_ledger_event():
    ep = _ep()
    f = LedgerTradeFact(episode_id="E1", realized_pnl=8.5, trade_id="F1")
    r = reconcile_episode_fields([ep], [f, f])
    assert any("duplicate_ledger_event" in i for i in r.issues)


def test_orphan_ledger():
    ep = _ep()
    facts = [LedgerTradeFact(episode_id="MISSING", realized_pnl=1.0, trade_id="FX")]
    r = reconcile_episode_fields([ep], facts)
    assert any("orphan_ledger" in i for i in r.issues)


def test_orphan_episode():
    ep = _ep()
    facts = [LedgerTradeFact(episode_id="OTHER", realized_pnl=1.0, trade_id="FX")]
    r = reconcile_episode_fields([ep], facts)
    assert any("orphan_episode" in i for i in r.issues)


def test_aggregate_pnl_mismatch():
    ep = _ep(pnl=10.0)
    r = reconcile_episode_pnl([ep], ledger_realized_pnl=50.0)
    assert not r.ok
    assert any("ledger_episode_mismatch" in i for i in r.issues)
