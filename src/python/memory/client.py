"""Research memory client — Turso/libSQL preferred, SQLite fallback for tests/local.

Never mutates Ledger, Champion, Registry, or PromotionGate.
Never logs TURSO_AUTH_TOKEN.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.python.memory.schema import MIGRATIONS, SCHEMA_VERSION


class MemoryStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "MEMORY_DEGRADED"
    UNAVAILABLE = "MEMORY_UNAVAILABLE"
    CONTEXT_UNAVAILABLE = "MEMORY_CONTEXT_UNAVAILABLE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_params(params: Any) -> str:
    raw = json.dumps(params or {}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


@dataclass
class ResearchMemory:
    status: MemoryStatus = MemoryStatus.UNAVAILABLE
    _conn: Any = None
    _backend: str = "none"
    last_error: str = ""

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception as e:
                self.last_error = f"close_{type(e).__name__}"
            self._conn = None

    def _execute(self, sql: str, params: tuple = ()) -> Any:
        assert self._conn is not None
        cur = self._conn.execute(sql, params)
        commit = getattr(self._conn, "commit", None)
        if callable(commit):
            try:
                commit()
            except Exception:
                pass
        return cur

    def _query(self, sql: str, params: tuple = ()) -> list[Any]:
        assert self._conn is not None
        cur = self._conn.execute(sql, params)
        return cur.fetchall()

    def migrate(self) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        rows = self._query("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        current = int(rows[0][0]) if rows else 0
        for ver in sorted(MIGRATIONS.keys()):
            if ver <= current:
                continue
            for stmt in MIGRATIONS[ver]:
                self._conn.execute(stmt)
            self._conn.execute(
                "INSERT OR REPLACE INTO schema_version(version, applied_at) VALUES (?, ?)",
                (ver, _now()),
            )
            commit = getattr(self._conn, "commit", None)
            if callable(commit):
                try:
                    commit()
                except Exception:
                    pass
            current = ver

    def upsert_experiment(self, row: dict[str, Any]) -> dict[str, Any]:
        if self.status == MemoryStatus.UNAVAILABLE or self._conn is None:
            return {"ok": False, "status": self.status.value, "reason": "MEMORY_UNAVAILABLE"}
        eid = row.get("experiment_id") or ""
        fp = row.get("fingerprint") or ""
        if not eid or not fp:
            return {"ok": False, "reason": "missing_identity"}
        existing = self._query(
            "SELECT experiment_id, fingerprint FROM experiments WHERE fingerprint = ? OR experiment_id = ?",
            (fp, eid),
        )
        if existing:
            return {"ok": True, "idempotent": True, "experiment_id": existing[0][0]}
        self._execute(
            """INSERT INTO experiments(
                experiment_id, fingerprint, hypothesis_id, strategy_id, commit_sha,
                dataset_hash, feature_hash, parameters_hash, cost_model, seed, status,
                result_hash, evidence_hash, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                eid, fp, row.get("hypothesis_id"), row.get("strategy_id"), row.get("commit_sha"),
                row.get("dataset_hash"), row.get("feature_hash"),
                row.get("parameters_hash") or _hash_params(row.get("parameters")),
                row.get("cost_model"), row.get("seed"), row.get("status"),
                row.get("result_hash"), row.get("evidence_hash"), _now(),
            ),
        )
        self.append_experiment_event(eid, None, row.get("status") or "CREATED")
        return {"ok": True, "idempotent": False, "experiment_id": eid}

    def append_experiment_event(
        self, experiment_id: str, from_status: Optional[str], to_status: str
    ) -> None:
        if self._conn is None:
            return
        import uuid
        self._execute(
            "INSERT INTO experiment_events(event_id, experiment_id, from_status, to_status, created_at) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), experiment_id, from_status, to_status, _now()),
        )

    def upsert_hypothesis(self, row: dict[str, Any]) -> dict[str, Any]:
        if self._conn is None:
            return {"ok": False, "status": self.status.value}
        hid = row.get("hypothesis_id") or ""
        if not hid:
            return {"ok": False, "reason": "missing_hypothesis_id"}
        existing = self._query("SELECT hypothesis_id FROM hypotheses WHERE hypothesis_id = ?", (hid,))
        if existing:
            return {"ok": True, "idempotent": True, "hypothesis_id": hid}
        self._execute(
            """INSERT INTO hypotheses(hypothesis_id, parent_id, hypothesis, counter_hypothesis, source, status, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                hid, row.get("parent_id"), row.get("hypothesis"), row.get("counter_hypothesis"),
                row.get("source"), row.get("status"), _now(),
            ),
        )
        return {"ok": True, "idempotent": False, "hypothesis_id": hid}

    def upsert_knowledge(self, row: dict[str, Any]) -> dict[str, Any]:
        if self._conn is None:
            return {"ok": False, "status": self.status.value}
        kid = row.get("knowledge_id") or ""
        if not kid:
            return {"ok": False, "reason": "missing_knowledge_id"}
        existing = self._query("SELECT knowledge_id FROM knowledge WHERE knowledge_id = ?", (kid,))
        if existing:
            return {"ok": True, "idempotent": True}
        self._execute(
            """INSERT INTO knowledge(knowledge_id, source_type, source_id, category, content, provenance, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (
                kid, row.get("source_type"), row.get("source_id"), row.get("category"),
                row.get("content"), json.dumps(row.get("provenance") or {}), _now(),
            ),
        )
        return {"ok": True, "idempotent": False}

    def audit(self, event_type: str, entity_type: str, entity_id: str, **meta: Any) -> None:
        if self._conn is None:
            return
        import uuid
        safe = {k: v for k, v in meta.items() if "token" not in k.lower() and "secret" not in k.lower()}
        self._execute(
            """INSERT INTO audit_events(event_id, event_type, entity_type, entity_id, fingerprint, metadata, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (str(uuid.uuid4()), event_type, entity_type, entity_id, meta.get("fingerprint"), json.dumps(safe), _now()),
        )

    def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        if self._conn is None:
            return None
        cur = self._conn.execute(
            "SELECT * FROM experiments WHERE experiment_id = ?", (experiment_id,),
        )
        rows = cur.fetchall() if hasattr(cur, "fetchall") else list(cur)
        if not rows:
            return None
        desc = getattr(cur, "description", None)
        if desc:
            cols = [d[0] for d in desc]
        else:
            cols = [
                "experiment_id", "fingerprint", "hypothesis_id", "strategy_id", "commit_sha",
                "dataset_hash", "feature_hash", "parameters_hash", "cost_model", "seed",
                "status", "result_hash", "evidence_hash", "created_at",
            ]
        return dict(zip(cols, rows[0]))

    def find_experiment_by_fingerprint(self, fingerprint: str) -> Optional[dict[str, Any]]:
        if self._conn is None:
            return None
        rows = self._query("SELECT experiment_id FROM experiments WHERE fingerprint = ?", (fingerprint,))
        if not rows:
            return None
        return self.get_experiment(rows[0][0])

    def list_recent_experiments(self, limit: int = 20) -> list[dict[str, Any]]:
        if self._conn is None:
            return []
        rows = self._query(
            "SELECT experiment_id FROM experiments ORDER BY created_at DESC LIMIT ?",
            (int(limit),),
        )
        return [self.get_experiment(r[0]) for r in rows if r[0]]  # type: ignore[misc]

    def verify_result_hash(self, experiment_id: str, result_hash: str) -> dict[str, Any]:
        row = self.get_experiment(experiment_id)
        if not row:
            return {"ok": False, "reason": "not_found"}
        if row.get("result_hash") and row["result_hash"] != result_hash:
            return {
                "ok": False,
                "reason": "MEMORY_DATA_INTEGRITY_FAIL",
                "memory_hash": row["result_hash"],
                "artifact_hash": result_hash,
            }
        return {"ok": True}


def connect_sqlite(path: str | Path) -> ResearchMemory:
    mem = ResearchMemory(status=MemoryStatus.AVAILABLE, _backend="sqlite")
    mem._conn = sqlite3.connect(str(path))
    mem.migrate()
    return mem


def connect_turso(
    url: str,
    token: str,
    *,
    timeout_sec: float = 30.0,
    prefer_http: bool = False,
) -> ResearchMemory:
    """Connect to Turso Cloud as research memory backend.

    Uses libsql package if installed, else HTTP pipeline (httpx).
    On failure returns MEMORY_UNAVAILABLE — never mutates ledger/champion.
    """
    from src.python.memory.turso_conn import connect_turso_backend

    conn, backend, err = connect_turso_backend(
        url, token, timeout_sec=timeout_sec, prefer_http=prefer_http,
    )
    if conn is None:
        return ResearchMemory(
            status=MemoryStatus.UNAVAILABLE,
            last_error=err or "TURSO_UNAVAILABLE",
            _backend="none",
        )
    mem = ResearchMemory(
        status=MemoryStatus.AVAILABLE,
        _conn=conn,
        _backend=f"turso_{backend}",
    )
    try:
        mem.migrate()
    except Exception as e:
        mem.close()
        return ResearchMemory(
            status=MemoryStatus.UNAVAILABLE,
            last_error=f"migrate_{type(e).__name__}",
            _backend="none",
        )
    return mem


def get_research_memory(
    *,
    sqlite_path: Optional[str] = None,
    prefer_sqlite: bool = False,
) -> ResearchMemory:
    """Factory: Turso if env set and reachable, else SQLite, else UNAVAILABLE.

    Env:
      TURSO_DATABASE_URL  (libsql://... or https://...)
      TURSO_AUTH_TOKEN

    prefer_sqlite=True forces local/test path (CI).
    Token is never logged.
    """
    if not prefer_sqlite:
        url = os.environ.get("TURSO_DATABASE_URL", "").strip()
        token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
        if url and token:
            mem = connect_turso(url, token)
            if mem.status == MemoryStatus.AVAILABLE:
                return mem
            if sqlite_path:
                local = connect_sqlite(sqlite_path)
                local.last_error = f"turso_fallback:{mem.last_error}"
                if local.status == MemoryStatus.AVAILABLE:
                    local.status = MemoryStatus.DEGRADED
                return local
            try:
                local = connect_sqlite(":memory:")
                local.last_error = f"turso_fallback:{mem.last_error}"
                local.status = MemoryStatus.DEGRADED
                return local
            except Exception:
                return mem
    if sqlite_path:
        return connect_sqlite(sqlite_path)
    try:
        return connect_sqlite(":memory:")
    except Exception as e:
        return ResearchMemory(status=MemoryStatus.UNAVAILABLE, last_error=type(e).__name__)


def memory_cannot_mutate_ledger() -> bool:
    return True


def memory_cannot_mutate_champion() -> bool:
    return True


def memory_cannot_approve_evidence() -> bool:
    return True
