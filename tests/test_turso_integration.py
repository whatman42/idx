"""Turso integration — HTTP mock, fallback, no authority."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from src.python.memory.client import (
    MemoryStatus,
    connect_sqlite,
    connect_turso,
    get_research_memory,
    memory_cannot_approve_evidence,
    memory_cannot_mutate_champion,
    memory_cannot_mutate_ledger,
)
from src.python.memory.queries import query_by_fingerprint, query_experiment, write_experiment
from src.python.memory.turso_conn import (
    TursoHttpConnection,
    _normalize_http_url,
    _pipeline_url,
    connect_turso_backend,
)


def test_normalize_libsql_url():
    assert _normalize_http_url("libsql://x.turso.io").startswith("https://")
    assert _pipeline_url("libsql://x.turso.io").endswith("/v2/pipeline")


def test_http_connect_auth_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.json.return_value = {}
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.return_value = mock_resp
        client_cls.return_value = client
        conn, backend, err = connect_turso_backend(
            "libsql://test.turso.io", "bad-token", prefer_http=True,
        )
    assert conn is None
    assert err == "AUTH_ERROR"
    assert backend == "none"


def test_http_connect_success_and_migrate():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "results": [{
            "type": "ok",
            "response": {
                "result": {
                    "cols": [{"name": "x"}],
                    "rows": [[{"type": "integer", "value": "1"}]],
                }
            },
        }]
    }
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.return_value = mock_resp
        client_cls.return_value = client
        mem = connect_turso("libsql://test.turso.io", "tok", prefer_http=True)
    assert mem.status == MemoryStatus.AVAILABLE
    assert mem._backend.startswith("turso_")
    mem.close()


def test_get_research_memory_without_env_is_sqlite():
    os.environ.pop("TURSO_DATABASE_URL", None)
    os.environ.pop("TURSO_AUTH_TOKEN", None)
    mem = get_research_memory(prefer_sqlite=True)
    assert mem.status in (MemoryStatus.AVAILABLE, MemoryStatus.DEGRADED)
    assert "turso" not in (mem._backend or "")


def test_config_error_missing_token():
    mem = connect_turso("libsql://x.turso.io", "")
    assert mem.status == MemoryStatus.UNAVAILABLE


def test_sqlite_still_works_as_memory(tmp_path):
    m = connect_sqlite(tmp_path / "t.db")
    w = write_experiment(m, {
        "experiment_id": "E-T",
        "fingerprint": "fp-t",
        "status": "COMPLETED",
        "result_hash": "rh",
    })
    assert w["persisted"] is True
    q = query_by_fingerprint(m, "fp-t")
    assert q["status"] == "MATCH_FOUND"
    assert query_experiment(m, "missing")["status"] == "NO_MATCH"


def test_turso_not_authority():
    assert memory_cannot_mutate_ledger() is True
    assert memory_cannot_mutate_champion() is True
    assert memory_cannot_approve_evidence() is True


def test_http_connection_never_logs_token():
    c = TursoHttpConnection(database_url="libsql://x", auth_token="SUPERSECRET")
    c.last_error = "AUTH_ERROR"
    assert "SUPERSECRET" not in c.last_error
