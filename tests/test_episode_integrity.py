"""Phase-1: one-fill-one-episode, idempotency, P&L reconciliation, paper-reset isolation."""
from __future__ import annotations

from src.python.learning.attribution import attribute_episode
from src.python.learning.episodes import (
    EpisodeStore,
    episode_from_closed_trade,
    ingest_closed_trades_from_portfolio,
    make_idempotency_key,
)
from src.python.learning.integrity import gate_learning_on_integrity, reconcile_episode_pnl
from src.python.learning.loop import LearningLoop
from src.python.ops.paper_portfolio import paper_reset_scope


def _exit_trade(**kw):
    base = {
        "trade_id": "tx_exit_001",
        "order_id": "ord_exit_001",
        "signal_id": "sig_bbca_1",
        "symbol": "BBCA",
        "side": -1,
        "action": "SELL",
        "qty": 500.0,
        "fill_price": 9700.0,
        "price": 9700.0,
        "pnl": -75_000.0,
        "cost_basis": 4_925_000.0,
        "fee": 12_125.0,
        "entry": 9850.0,
        "tp": 10441.0,
        "sl": 9555.0,
        "reason": "SL_HIT",
        "timestamp": "2026-09-19",
        "status": "FILLED",
    }
    base.update(kw)
    return base


def _entry_trade(**kw):
    base = {
        "trade_id": "tx_entry_001",
        "order_id": "ord_entry_001",
        "signal_id": "sig_bbca_1",
        "symbol": "BBCA",
        "side": 1,
        "action": "BUY",
        "qty": 500.0,
        "fill_price": 9850.0,
        "fee": 7_387.5,
        "timestamp": "2026-09-18",
        "status": "FILLED",
    }
    base.update(kw)
    return base


def test_one_fill_one_episode():
    ep = episode_from_closed_trade(_exit_trade(), entry_trade=_entry_trade(), strategy_id="rule_sma20")
    assert ep.lifecycle == "COMPLETED"
    assert ep.fill_id == "tx_exit_001"
    assert ep.signal_id == "sig_bbca_1"
    assert ep.idempotency_key
    assert ep.outcome == "LOSS"
    assert ep.pnl == -75_000.0


def test_idempotency_same_fill_twice():
    store = EpisodeStore()
    trades = [_entry_trade(), _exit_trade()]
    r1 = ingest_closed_trades_from_portfolio(trades, store=store, strategy_id="rule_sma20")
    r2 = ingest_closed_trades_from_portfolio(trades, store=store, strategy_id="rule_sma20")
    assert r1["created"] == 1
    assert r2["created"] == 0
    assert r2["skipped_duplicates"] == 1
    assert len(store.list_completed()) == 1
    assert store.list_completed()[0].episode_id == r1["new_episodes"][0]["episode_id"]


def test_distinct_fills_produce_distinct_episodes():
    store = EpisodeStore()
    t1 = [_entry_trade(), _exit_trade()]
    t2 = [
        _entry_trade(trade_id="tx_entry_002", signal_id="sig_bbri_1", symbol="BBRI"),
        _exit_trade(trade_id="tx_exit_002", signal_id="sig_bbri_1", symbol="BBRI", pnl=-10_000.0),
    ]
    ingest_closed_trades_from_portfolio(t1, store=store)
    ingest_closed_trades_from_portfolio(t2, store=store)
    assert len(store.list_completed()) == 2
    ids = {e.episode_id for e in store.list_completed()}
    keys = {e.idempotency_key for e in store.list_completed()}
    assert len(ids) == 2
    assert len(keys) == 2


def test_missing_exit_not_completed():
    ep = episode_from_closed_trade(_entry_trade(action="BUY"), entry_trade=None)
    assert ep.lifecycle == "INVALID"
    assert ep.outcome == "SKIPPED"


def test_pnl_reconciliation_pass():
    ep = episode_from_closed_trade(_exit_trade(pnl=-50_000.0), entry_trade=_entry_trade())
    attr = attribute_episode(ep)
    assert attr.pnl == ep.pnl
    result = reconcile_episode_pnl([ep], closed_trade_pnls=[-50_000.0], attributions=[attr])
    assert result.learning_data_integrity == "PASS"
    assert result.ok is True
    assert gate_learning_on_integrity(result)["learning_update"] == "ALLOW"


def test_pnl_reconciliation_fail_blocks_learning():
    ep = episode_from_closed_trade(_exit_trade(pnl=-50_000.0), entry_trade=_entry_trade())
    result = reconcile_episode_pnl([ep], closed_trade_pnls=[-10_000.0])
    assert result.learning_data_integrity == "FAIL"
    assert result.blocked is True
    gate = gate_learning_on_integrity(result)
    assert gate["learning_update"] == "BLOCKED"
    assert gate["experiment_promotion"] == "BLOCKED"


def test_learning_loop_ingest_blocks_on_mismatch():
    loop = LearningLoop()
    trades = [_entry_trade(), _exit_trade(pnl=-50_000.0)]
    out = loop.ingest_from_paper_trades(trades)
    assert out["principle"] == "research_only_no_execution"
    assert out["integrity"]["learning_data_integrity"] == "PASS"


def test_paper_reset_preserves_learning_paths():
    scope = paper_reset_scope()
    assert scope["resets"] == "PAPER_ACCOUNT_STATE_ONLY"
    assert any("learning" in p for p in scope["protected_path_prefixes"])
    does_not = " ".join(scope["does_not"]).lower()
    assert "production" in does_not or "model" in does_not


def test_attribution_pnl_matches_episode():
    ep = episode_from_closed_trade(_exit_trade(pnl=-12_345.0), entry_trade=_entry_trade())
    a = attribute_episode(ep)
    assert a.pnl == ep.pnl == -12_345.0


def test_idempotency_key_stable():
    k1 = make_idempotency_key(
        signal_id="s1", symbol="BBCA", entry_trade_id="e1", exit_trade_id="x1", session_id="sess"
    )
    k2 = make_idempotency_key(
        signal_id="s1", symbol="BBCA", entry_trade_id="e1", exit_trade_id="x1", session_id="sess"
    )
    assert k1 == k2
    k3 = make_idempotency_key(
        signal_id="s1", symbol="BBCA", entry_trade_id="e1", exit_trade_id="x2", session_id="sess"
    )
    assert k1 != k3


def test_deterministic_episode_id():
    ep1 = episode_from_closed_trade(_exit_trade(), entry_trade=_entry_trade())
    ep2 = episode_from_closed_trade(_exit_trade(), entry_trade=_entry_trade())
    assert ep1.episode_id == ep2.episode_id
    assert ep1.idempotency_key == ep2.idempotency_key
