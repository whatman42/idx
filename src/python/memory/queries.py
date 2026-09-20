"""Structured research-memory queries and writes.

NO_MATCH != MEMORY_UNAVAILABLE.
persisted=True does NOT imply remote_persisted=True.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from src.python.memory.client import MemoryStatus, ResearchMemory


def _backend_label(mem: ResearchMemory) -> str:
    b = mem._backend or "none"
    if b.startswith("turso_"):
        return "turso"
    if b == "sqlite_fallback" or (b.startswith("sqlite") and mem.status == MemoryStatus.DEGRADED):
        return "sqlite_fallback"
    if b.startswith("sqlite"):
        return "sqlite"
    return b or "none"


def _write_result(
    mem: ResearchMemory,
    *,
    ok: bool,
    status: str,
    idempotent: bool = False,
    entity_id: str = "",
    reason: str = "",
    error_type: str = "",
) -> dict[str, Any]:
    backend = _backend_label(mem)
    remote = bool(ok and getattr(mem, "is_remote", False) and mem.status == MemoryStatus.AVAILABLE)
    local = bool(ok and getattr(mem, "is_local", b.startswith("sqlite") if (b := mem._backend or "") else False))
    if ok and mem.status == MemoryStatus.DEGRADED:
        remote = False
        local = True
        if backend == "sqlite":
            backend = "sqlite_fallback"
        status = "LOCAL_ONLY" if status == "MEMORY_WRITE_SUCCESS" else status
    # plain sqlite available
    if ok and mem.status == MemoryStatus.AVAILABLE and (mem._backend or "").startswith("sqlite"):
        remote = False
        local = True
    out: dict[str, Any] = {
        "status": status,
        "ok": ok,
        "persisted": bool(ok),
        "remote_persisted": remote,
        "local_persisted": local,
        "backend": backend,
        "idempotent": idempotent,
    }
    if entity_id:
        out["entity_id"] = entity_id
    if reason:
        out["reason"] = reason
    if error_type:
        out["error_type"] = error_type
    return out


def _read_unavailable(error_type: str = "") -> dict[str, Any]:
    return {
        "status": "MEMORY_UNAVAILABLE",
        "match": False,
        "records": [],
        "record": None,
        "experiment": None,
        "persisted": False,
        "error_type": error_type,
    }


def _read_no_match() -> dict[str, Any]:
    return {
        "status": "NO_MATCH",
        "match": False,
        "records": [],
        "record": None,
        "experiment": None,
        "persisted": True,
    }


def _read_match(record: Any = None, records: Optional[list] = None) -> dict[str, Any]:
    recs = records if records is not None else ([record] if record is not None else [])
    return {
        "status": "MATCH_FOUND",
        "match": True,
        "records": recs,
        "record": recs[0] if recs else record,
        "experiment": recs[0] if recs else record,
        "persisted": True,
    }


def query_experiment(mem: ResearchMemory, experiment_id: str) -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _read_unavailable()
    try:
        row = mem.get_experiment(experiment_id)
    except Exception as e:
        mem.last_error = type(e).__name__
        return _read_unavailable(type(e).__name__)
    if row is None:
        return _read_no_match()
    return _read_match(record=row)


def query_by_fingerprint(mem: ResearchMemory, fingerprint: str) -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _read_unavailable()
    try:
        row = mem.find_experiment_by_fingerprint(fingerprint)
    except Exception as e:
        mem.last_error = type(e).__name__
        return _read_unavailable(type(e).__name__)
    if row is None:
        return _read_no_match()
    return _read_match(record=row)


def write_experiment(mem: ResearchMemory, row: dict[str, Any]) -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _write_result(mem, ok=False, status="MEMORY_UNAVAILABLE")
    try:
        out = mem.upsert_experiment(row)
        if out.get("ok"):
            return _write_result(
                mem, ok=True, status="MEMORY_WRITE_SUCCESS",
                idempotent=bool(out.get("idempotent")),
                entity_id=str(out.get("experiment_id") or row.get("experiment_id") or ""),
            )
        return _write_result(mem, ok=False, status="MEMORY_WRITE_FAILED", reason=out.get("reason", "write_failed"))
    except Exception as e:
        mem.last_error = type(e).__name__
        return _write_result(mem, ok=False, status="MEMORY_WRITE_FAILED", error_type=type(e).__name__)


def write_hypothesis(mem: ResearchMemory, row: dict[str, Any]) -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _write_result(mem, ok=False, status="MEMORY_UNAVAILABLE")
    try:
        out = mem.upsert_hypothesis(row)
        if out.get("ok"):
            return _write_result(
                mem, ok=True, status="MEMORY_WRITE_SUCCESS",
                idempotent=bool(out.get("idempotent")),
                entity_id=str(out.get("hypothesis_id") or row.get("hypothesis_id") or ""),
            )
        return _write_result(mem, ok=False, status="MEMORY_WRITE_FAILED", reason=out.get("reason", ""))
    except Exception as e:
        return _write_result(mem, ok=False, status="MEMORY_WRITE_FAILED", error_type=type(e).__name__)


def query_hypotheses(mem: ResearchMemory, hypothesis_id: str = "") -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _read_unavailable()
    try:
        if hypothesis_id:
            rows = mem._query(
                "SELECT hypothesis_id, parent_id, hypothesis, counter_hypothesis, source, status, created_at FROM hypotheses WHERE hypothesis_id = ?",
                (hypothesis_id,),
            )
        else:
            rows = mem._query(
                "SELECT hypothesis_id, parent_id, hypothesis, counter_hypothesis, source, status, created_at FROM hypotheses ORDER BY created_at DESC LIMIT 50"
            )
        cols = ["hypothesis_id", "parent_id", "hypothesis", "counter_hypothesis", "source", "status", "created_at"]
        records = [dict(zip(cols, r)) for r in rows]
        if not records:
            return _read_no_match()
        return _read_match(records=records)
    except Exception as e:
        return _read_unavailable(type(e).__name__)


def write_failure(mem: ResearchMemory, row: dict[str, Any]) -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _write_result(mem, ok=False, status="MEMORY_UNAVAILABLE")
    fid = row.get("failure_id") or ""
    if not fid:
        return _write_result(mem, ok=False, status="MEMORY_WRITE_FAILED", reason="missing_failure_id")
    try:
        existing = mem._query("SELECT failure_id FROM failures WHERE failure_id = ?", (fid,))
        if existing:
            return _write_result(mem, ok=True, status="MEMORY_WRITE_SUCCESS", idempotent=True, entity_id=fid)
        mem._execute(
            "INSERT INTO failures(failure_id, episode_id, signal_id, failure_type, attribution, created_at) VALUES (?,?,?,?,?,?)",
            (fid, row.get("episode_id"), row.get("signal_id"), row.get("failure_type"),
             row.get("attribution") if isinstance(row.get("attribution"), str) else json.dumps(row.get("attribution") or {}),
             row.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )
        return _write_result(mem, ok=True, status="MEMORY_WRITE_SUCCESS", entity_id=fid)
    except Exception as e:
        return _write_result(mem, ok=False, status="MEMORY_WRITE_FAILED", error_type=type(e).__name__)


def query_failures(mem: ResearchMemory, failure_id: str = "") -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _read_unavailable()
    try:
        if failure_id:
            rows = mem._query(
                "SELECT failure_id, episode_id, signal_id, failure_type, attribution, created_at FROM failures WHERE failure_id = ?",
                (failure_id,),
            )
        else:
            rows = mem._query(
                "SELECT failure_id, episode_id, signal_id, failure_type, attribution, created_at FROM failures ORDER BY created_at DESC LIMIT 50"
            )
        cols = ["failure_id", "episode_id", "signal_id", "failure_type", "attribution", "created_at"]
        records = [dict(zip(cols, r)) for r in rows]
        if not records:
            return _read_no_match()
        return _read_match(records=records)
    except Exception as e:
        return _read_unavailable(type(e).__name__)


def write_knowledge(mem: ResearchMemory, row: dict[str, Any]) -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _write_result(mem, ok=False, status="MEMORY_UNAVAILABLE")
    try:
        out = mem.upsert_knowledge(row)
        if out.get("ok"):
            return _write_result(mem, ok=True, status="MEMORY_WRITE_SUCCESS", idempotent=bool(out.get("idempotent")), entity_id=str(row.get("knowledge_id") or ""))
        return _write_result(mem, ok=False, status="MEMORY_WRITE_FAILED", reason=out.get("reason", ""))
    except Exception as e:
        return _write_result(mem, ok=False, status="MEMORY_WRITE_FAILED", error_type=type(e).__name__)


def query_knowledge(mem: ResearchMemory, knowledge_id: str = "") -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _read_unavailable()
    try:
        if knowledge_id:
            rows = mem._query(
                "SELECT knowledge_id, source_type, source_id, category, content, provenance, created_at FROM knowledge WHERE knowledge_id = ?",
                (knowledge_id,),
            )
        else:
            rows = mem._query(
                "SELECT knowledge_id, source_type, source_id, category, content, provenance, created_at FROM knowledge ORDER BY created_at DESC LIMIT 50"
            )
        cols = ["knowledge_id", "source_type", "source_id", "category", "content", "provenance", "created_at"]
        records = [dict(zip(cols, r)) for r in rows]
        if not records:
            return _read_no_match()
        return _read_match(records=records)
    except Exception as e:
        return _read_unavailable(type(e).__name__)


def write_drift(mem: ResearchMemory, row: dict[str, Any]) -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _write_result(mem, ok=False, status="MEMORY_UNAVAILABLE")
    did = row.get("drift_id") or ""
    if not did:
        return _write_result(mem, ok=False, status="MEMORY_WRITE_FAILED", reason="missing_drift_id")
    try:
        existing = mem._query("SELECT drift_id FROM drift_events WHERE drift_id = ?", (did,))
        if existing:
            return _write_result(mem, ok=True, status="MEMORY_WRITE_SUCCESS", idempotent=True, entity_id=did)
        mem._execute(
            "INSERT INTO drift_events(drift_id, metric, baseline, observed, regime, created_at) VALUES (?,?,?,?,?,?)",
            (did, row.get("metric"), row.get("baseline"), row.get("observed"), row.get("regime"),
             row.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )
        return _write_result(mem, ok=True, status="MEMORY_WRITE_SUCCESS", entity_id=did)
    except Exception as e:
        return _write_result(mem, ok=False, status="MEMORY_WRITE_FAILED", error_type=type(e).__name__)


def query_drift(mem: ResearchMemory, drift_id: str = "") -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _read_unavailable()
    try:
        if drift_id:
            rows = mem._query(
                "SELECT drift_id, metric, baseline, observed, regime, created_at FROM drift_events WHERE drift_id = ?",
                (drift_id,),
            )
        else:
            rows = mem._query(
                "SELECT drift_id, metric, baseline, observed, regime, created_at FROM drift_events ORDER BY created_at DESC LIMIT 50"
            )
        cols = ["drift_id", "metric", "baseline", "observed", "regime", "created_at"]
        records = [dict(zip(cols, r)) for r in rows]
        if not records:
            return _read_no_match()
        return _read_match(records=records)
    except Exception as e:
        return _read_unavailable(type(e).__name__)


def query_experiment_events(mem: ResearchMemory, experiment_id: str = "") -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _read_unavailable()
    try:
        if experiment_id:
            rows = mem._query(
                "SELECT event_id, experiment_id, from_status, to_status, created_at FROM experiment_events WHERE experiment_id = ? ORDER BY created_at",
                (experiment_id,),
            )
        else:
            rows = mem._query(
                "SELECT event_id, experiment_id, from_status, to_status, created_at FROM experiment_events ORDER BY created_at DESC LIMIT 50"
            )
        cols = ["event_id", "experiment_id", "from_status", "to_status", "created_at"]
        records = [dict(zip(cols, r)) for r in rows]
        if not records:
            return _read_no_match()
        return _read_match(records=records)
    except Exception as e:
        return _read_unavailable(type(e).__name__)


def query_audit_events(mem: ResearchMemory, entity_id: str = "") -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return _read_unavailable()
    try:
        if entity_id:
            rows = mem._query(
                "SELECT event_id, event_type, entity_type, entity_id, fingerprint, metadata, created_at FROM audit_events WHERE entity_id = ? ORDER BY created_at DESC LIMIT 50",
                (entity_id,),
            )
        else:
            rows = mem._query(
                "SELECT event_id, event_type, entity_type, entity_id, fingerprint, metadata, created_at FROM audit_events ORDER BY created_at DESC LIMIT 50"
            )
        cols = ["event_id", "event_type", "entity_type", "entity_id", "fingerprint", "metadata", "created_at"]
        records = [dict(zip(cols, r)) for r in rows]
        if not records:
            return _read_no_match()
        return _read_match(records=records)
    except Exception as e:
        return _read_unavailable(type(e).__name__)
