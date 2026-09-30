"""Operational Awareness — read-only diagnosis, not a decision maker."""
from __future__ import annotations

from src.python.crypto.operational_awareness import build_cycle_awareness


def test_awareness_read_only_flags():
    rep = {
        "status": "SUCCESS",
        "cycle_id": "CRYPTO-TEST-1",
        "live_execution": False,
        "signals_count": 2,
        "fills_paper": 1,
        "data_quality_blocks": 0,
        "risk_skips": 0,
        "governor_blocks": 0,
        "gate_blocks": 0,
        "execution_policy": "NEXT_BAR_OPEN",
        "portfolio": {"cash": 9000.0, "market_value": 1000.0, "equity": 10000.0, "positions": {}},
        "universe": {"eligible_count": 10, "discovered_count": 12},
    }
    a = build_cycle_awareness(rep, persist_snapshot=False)
    assert a["read_only"] is True
    assert a["can_mutate_strategy"] is False
    assert a["can_mutate_ledger"] is False
    assert a["can_mutate_promotion"] is False
    assert a["live_execution"] is False
    assert a["system_health"] in ("HEALTHY", "DEGRADED", "BLOCKED")
    assert "what_i_saw" in a and "what_i_refused" in a
    assert a["what_i_executed"]["same_bar_fill"] is False


def test_awareness_degraded_on_blocks():
    rep = {
        "status": "SUCCESS",
        "cycle_id": "CRYPTO-TEST-2",
        "data_quality_blocks": 3,
        "risk_blocks": 1,
        "governor_blocks": 0,
        "gate_blocks": 2,
        "fills_paper": 0,
        "signals_count": 5,
        "portfolio": {"cash": 10000, "equity": 10000, "positions": {}},
        "universe": {},
    }
    a = build_cycle_awareness(rep, persist_snapshot=False)
    assert a["system_health"] == "DEGRADED"
    assert any("DATA_QUALITY" in r for r in a["health_reasons"])


def test_awareness_blocked_on_provider_fail():
    a = build_cycle_awareness(
        {"status": "FAIL_CLOSED_PROVIDER", "cycle_id": "X", "portfolio": {}, "universe": {}},
        persist_snapshot=False,
    )
    assert a["system_health"] == "BLOCKED"


def test_awareness_not_imported_as_mutator():
    import inspect
    import src.python.crypto.operational_awareness as oa

    src = inspect.getsource(oa)
    assert "apply_buy" not in src
    assert "set_status" not in src
    assert "CRYPTO_EXECUTION_POLICY =" not in src
