"""Crypto Research Memory — Turso/SQLite, optional for paper ops.

Authority bounds (locked):
  Turso  ≠ Ledger
  Memory ≠ Order / LIVE_EXECUTION / Champion IDX
  If Turso DOWN → research write fails soft; crypto paper continues.

Tables (namespace crypto_* only — never IDX experiments/hypotheses):
  crypto_schema_version
  crypto_experiments
  crypto_evidence
  crypto_cycle_logs
  crypto_strategy_versions
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

CRYPTO_MEMORY_SCHEMA_VERSION = 1

CRYPTO_MIGRATIONS: dict[int, list[str]] = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS crypto_schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS crypto_experiments (
            experiment_id TEXT PRIMARY KEY,
            fingerprint TEXT NOT NULL,
            strategy_id TEXT,
            strategy_version TEXT,
            commit_sha TEXT,
            dataset_hash TEXT,
            parameters_hash TEXT,
            cost_model TEXT,
            status TEXT,
            result_hash TEXT,
            evidence_hash TEXT,
            market TEXT DEFAULT 'CRYPTO',
            quote_currency TEXT DEFAULT 'USDT',
            created_at TEXT NOT NULL,
            UNIQUE(fingerprint)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS crypto_evidence (
            evidence_id TEXT PRIMARY KEY,
            strategy_id TEXT NOT NULL,
            strategy_version TEXT,
            package_hash TEXT,
            payload_json TEXT,
            origin TEXT DEFAULT 'CORE',
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS crypto_cycle_logs (
            cycle_id TEXT PRIMARY KEY,
            trading_date TEXT,
            status TEXT,
            signal_coverage TEXT,
            signal_coverage_mode TEXT,
            eligible_count INTEGER,
            ohlcv_ok INTEGER,
            signals_count INTEGER,
            fills_paper INTEGER,
            equity_usdt REAL,
            live_execution INTEGER DEFAULT 0,
            report_hash TEXT,
            payload_json TEXT,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS crypto_strategy_versions (
            strategy_id TEXT NOT NULL,
            strategy_version TEXT NOT NULL,
            lifecycle TEXT DEFAULT 'RESEARCH',
            notes TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (strategy_id, strategy_version)
        )
        """,
    ],
}


class CryptoMemoryStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class CryptoResearchMemory:
    """Optional research SSOT for crypto. Never mutates CryptoPaperLedger."""

    status: CryptoMemoryStatus = CryptoMemoryStatus.UNAVAILABLE
    _conn: Any = None
    _backend: str = "none"
    last_error: str = ""
    can_mutate_ledger: bool = False
    can_mutate_live_execution: bool = False
    can_submit_orders: bool = False

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def migrate(self) -> None:
        if self._conn is None:
            return
        cur = self._conn.cursor()
        try:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS crypto_schema_version "
                "(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            cur.execute("SELECT COALESCE(MAX(version), 0) FROM crypto_schema_version")
            row = cur.fetchone()
            current = int(row[0] if row else 0)
        except Exception:
            current = 0
        for ver in sorted(CRYPTO_MIGRATIONS.keys()):
            if ver <= current:
                continue
            for stmt in CRYPTO_MIGRATIONS[ver]:
                cur.execute(stmt)
            cur.execute(
                "INSERT OR REPLACE INTO crypto_schema_version(version, applied_at) VALUES (?, ?)",
                (ver, _now()),
            )
        try:
            self._conn.commit()
        except Exception:
            pass

    def _exec(self, sql: str, params: tuple = ()) -> bool:
        if self._conn is None or self.status == CryptoMemoryStatus.UNAVAILABLE:
            return False
        try:
            self._conn.execute(sql, params)
            self._conn.commit()
            return True
        except Exception as e:
            self.last_error = f"{type(e).__name__}:{e}"
            return False

    def record_cycle(self, report: dict[str, Any]) -> dict[str, Any]:
        if self.status == CryptoMemoryStatus.UNAVAILABLE:
            return {"ok": False, "reason": "MEMORY_UNAVAILABLE", "paper_blocked": False}
        uni = report.get("universe") or {}
        pf = report.get("portfolio") or {}
        cycle_id = str(
            report.get("cycle_id")
            or f"crypto-{report.get('generated_at', _now())[:19]}"
        )
        payload = {
            "status": report.get("status"),
            "signal_coverage": report.get("signal_coverage"),
            "fills_paper": report.get("fills_paper"),
            "strategy_id": report.get("strategy_id"),
            "live_execution": False,
        }
        rh = _hash(payload)[:32]
        ok = self._exec(
            """
            INSERT OR REPLACE INTO crypto_cycle_logs(
                cycle_id, trading_date, status, signal_coverage, signal_coverage_mode,
                eligible_count, ohlcv_ok, signals_count, fills_paper, equity_usdt,
                live_execution, report_hash, payload_json, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,0,?,?,?)
            """,
            (
                cycle_id,
                str(report.get("generated_at") or "")[:10],
                str(report.get("status") or ""),
                str(report.get("signal_coverage") or ""),
                str(report.get("signal_coverage_mode") or ""),
                int(uni.get("eligible_count") or report.get("ohlcv_attempted") or 0),
                int(report.get("ohlcv_ok") or 0),
                int(report.get("signals_count") or 0),
                int(report.get("fills_paper") or 0),
                float(pf.get("equity") or 0),
                rh,
                json.dumps(payload, default=str),
                _now(),
            ),
        )
        return {
            "ok": ok,
            "cycle_id": cycle_id,
            "report_hash": rh,
            "backend": self._backend,
            "status": self.status.value,
            "paper_blocked": False,
            "error": self.last_error if not ok else "",
        }

    def record_strategy_version(
        self,
        strategy_id: str,
        strategy_version: str,
        *,
        lifecycle: str = "RESEARCH",
        notes: str = "",
    ) -> bool:
        return self._exec(
            """
            INSERT OR REPLACE INTO crypto_strategy_versions(
                strategy_id, strategy_version, lifecycle, notes, created_at
            ) VALUES (?,?,?,?,?)
            """,
            (strategy_id, strategy_version, lifecycle, notes, _now()),
        )

    def record_evidence(
        self,
        *,
        evidence_id: str,
        strategy_id: str,
        strategy_version: str = "",
        payload: Optional[dict] = None,
        origin: str = "CORE",
    ) -> bool:
        body = payload or {}
        ph = _hash(body)[:32]
        return self._exec(
            """
            INSERT OR REPLACE INTO crypto_evidence(
                evidence_id, strategy_id, strategy_version, package_hash,
                payload_json, origin, created_at
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                evidence_id,
                strategy_id,
                strategy_version,
                ph,
                json.dumps(body, default=str),
                origin,
                _now(),
            ),
        )


def connect_crypto_sqlite(path: str = ":memory:") -> CryptoResearchMemory:
    mem = CryptoResearchMemory(status=CryptoMemoryStatus.AVAILABLE, _backend="sqlite")
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    mem._conn = sqlite3.connect(path)
    mem.migrate()
    return mem


def connect_crypto_turso(url: str, token: str) -> CryptoResearchMemory:
    try:
        from src.python.memory.turso_conn import connect_turso_backend
    except Exception as e:
        return CryptoResearchMemory(
            status=CryptoMemoryStatus.UNAVAILABLE,
            last_error=f"import_turso:{type(e).__name__}",
        )
    conn, backend, err = connect_turso_backend(url, token, timeout_sec=30.0)
    if conn is None:
        return CryptoResearchMemory(
            status=CryptoMemoryStatus.UNAVAILABLE,
            last_error=err or "TURSO_UNAVAILABLE",
        )
    mem = CryptoResearchMemory(
        status=CryptoMemoryStatus.AVAILABLE,
        _conn=conn,
        _backend=f"turso_{backend}",
    )
    try:
        mem.migrate()
    except Exception as e:
        mem.close()
        return CryptoResearchMemory(
            status=CryptoMemoryStatus.UNAVAILABLE,
            last_error=f"migrate_{type(e).__name__}",
        )
    return mem


def get_crypto_research_memory(
    *,
    sqlite_path: Optional[str] = None,
    prefer_sqlite: bool = False,
) -> CryptoResearchMemory:
    if not prefer_sqlite:
        url = os.environ.get("TURSO_DATABASE_URL", "").strip()
        token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
        url = os.environ.get("CRYPTO_TURSO_DATABASE_URL", url).strip() or url
        token = os.environ.get("CRYPTO_TURSO_AUTH_TOKEN", token).strip() or token
        if url and token:
            mem = connect_crypto_turso(url, token)
            if mem.status == CryptoMemoryStatus.AVAILABLE:
                return mem
            path = sqlite_path or os.environ.get(
                "CRYPTO_MEMORY_SQLITE", "state/crypto/research_memory.sqlite"
            )
            local = connect_crypto_sqlite(path)
            local.last_error = f"turso_fallback:{mem.last_error}"
            local._backend = "sqlite_fallback"
            local.status = CryptoMemoryStatus.DEGRADED
            return local
    path = sqlite_path or os.environ.get(
        "CRYPTO_MEMORY_SQLITE", "state/crypto/research_memory.sqlite"
    )
    try:
        return connect_crypto_sqlite(path if path else ":memory:")
    except Exception as e:
        return CryptoResearchMemory(
            status=CryptoMemoryStatus.UNAVAILABLE, last_error=type(e).__name__
        )


def crypto_memory_cannot_mutate_ledger() -> bool:
    return True


def crypto_memory_cannot_enable_live() -> bool:
    return True
