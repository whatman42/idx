"""Structured research-memory queries.

MEMORY_UNAVAILABLE ≠ NO_MATCH.
Write failure ≠ persisted.
"""
from __future__ import annotations

from typing import Any

from src.python.memory.client import MemoryStatus, ResearchMemory


def query_experiment(mem: ResearchMemory, experiment_id: str) -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return {
            "status": "MEMORY_UNAVAILABLE",
            "match": False,
            "experiment": None,
            "persisted": False,
        }
    try:
        row = mem.get_experiment(experiment_id)
    except Exception as e:
        mem.last_error = type(e).__name__
        return {
            "status": "MEMORY_UNAVAILABLE",
            "match": False,
            "experiment": None,
            "persisted": False,
            "error_type": type(e).__name__,
        }
    if row is None:
        return {"status": "NO_MATCH", "match": False, "experiment": None, "persisted": True}
    return {"status": "MATCH_FOUND", "match": True, "experiment": row, "persisted": True}


def query_by_fingerprint(mem: ResearchMemory, fingerprint: str) -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return {
            "status": "MEMORY_UNAVAILABLE",
            "match": False,
            "experiment": None,
            "persisted": False,
        }
    try:
        row = mem.find_experiment_by_fingerprint(fingerprint)
    except Exception as e:
        mem.last_error = type(e).__name__
        return {
            "status": "MEMORY_UNAVAILABLE",
            "match": False,
            "experiment": None,
            "persisted": False,
            "error_type": type(e).__name__,
        }
    if row is None:
        return {"status": "NO_MATCH", "match": False, "experiment": None, "persisted": True}
    return {"status": "MATCH_FOUND", "match": True, "experiment": row, "persisted": True}


def write_experiment(mem: ResearchMemory, row: dict[str, Any]) -> dict[str, Any]:
    if mem.status == MemoryStatus.UNAVAILABLE or mem._conn is None:
        return {"status": "MEMORY_UNAVAILABLE", "persisted": False, "ok": False}
    try:
        out = mem.upsert_experiment(row)
        if out.get("ok"):
            return {
                "status": "MEMORY_WRITE_SUCCESS",
                "persisted": True,
                "ok": True,
                "idempotent": bool(out.get("idempotent")),
                "experiment_id": out.get("experiment_id"),
            }
        return {
            "status": "MEMORY_WRITE_FAILED",
            "persisted": False,
            "ok": False,
            "reason": out.get("reason", "write_failed"),
        }
    except Exception as e:
        mem.last_error = type(e).__name__
        return {
            "status": "MEMORY_WRITE_FAILED",
            "persisted": False,
            "ok": False,
            "error_type": type(e).__name__,
        }
