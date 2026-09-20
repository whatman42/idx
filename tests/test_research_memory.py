"""Turso/SQLite research memory — isolation, idempotency, failure modes."""
from __future__ import annotations

import os

from src.python.memory.client import (
    MemoryStatus,
    ResearchMemory,
    connect_sqlite,
    get_research_memory,
    memory_cannot_approve_evidence,
    memory_cannot_mutate_champion,
    memory_cannot_mutate_ledger,
)


def test_schema_migrate_idempotent(tmp_path):
    db = tmp_path / "m.db"
    m1 = connect_sqlite(db)
    m2 = connect_sqlite(db)
    assert m1.status == MemoryStatus.AVAILABLE
    m1.close()
    m2.close()


def test_experiment_idempotent_by_fingerprint(tmp_path):
    m = connect_sqlite(tmp_path / "e.db")
    row = {
        "experiment_id": "EXP-1",
        "fingerprint": "fp-abc",
        "strategy_id": "sma",
        "status": "COMPLETED",
        "result_hash": "rh1",
        "seed": 1,
        "cost_model": "simulation_v2",
    }
    r1 = m.upsert_experiment(row)
    r2 = m.upsert_experiment(row)
    assert r1["ok"] and not r1.get("idempotent")
    assert r2["idempotent"] is True
    assert len(m.list_recent_experiments()) == 1


def test_result_hash_integrity(tmp_path):
    m = connect_sqlite(tmp_path / "h.db")
    m.upsert_experiment({
        "experiment_id": "EXP-H", "fingerprint": "fp-h", "result_hash": "AAA", "status": "COMPLETED",
    })
    bad = m.verify_result_hash("EXP-H", "BBB")
    assert bad["ok"] is False
    assert bad["reason"] == "MEMORY_DATA_INTEGRITY_FAIL"
    good = m.verify_result_hash("EXP-H", "AAA")
    assert good["ok"] is True


def test_parameterized_no_injection(tmp_path):
    m = connect_sqlite(tmp_path / "s.db")
    evil = "x'); DROP TABLE experiments;--"
    m.upsert_experiment({"experiment_id": evil, "fingerprint": "fp-evil", "status": "FAILED"})
    assert m.get_experiment(evil) is not None
    assert m.find_experiment_by_fingerprint("fp-evil") is not None


def test_missing_env_safe():
    os.environ.pop("TURSO_DATABASE_URL", None)
    os.environ.pop("TURSO_AUTH_TOKEN", None)
    m = get_research_memory()
    assert m.status in (MemoryStatus.AVAILABLE, MemoryStatus.UNAVAILABLE, MemoryStatus.DEGRADED)


def test_boundary_flags():
    assert memory_cannot_mutate_ledger() is True
    assert memory_cannot_mutate_champion() is True
    assert memory_cannot_approve_evidence() is True


def test_unavailable_write_does_not_raise():
    m = ResearchMemory(status=MemoryStatus.UNAVAILABLE)
    out = m.upsert_experiment({"experiment_id": "X", "fingerprint": "Y"})
    assert out["ok"] is False
    assert out["status"] == MemoryStatus.UNAVAILABLE.value
