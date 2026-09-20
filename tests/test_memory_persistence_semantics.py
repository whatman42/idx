"""P0: remote_persisted vs local_persisted; full query API; HTTP errors; isolation."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.python.memory.client import (
    MemoryStatus,
    ResearchMemory,
    connect_sqlite,
    connect_turso,
    memory_cannot_approve_evidence,
    memory_cannot_mutate_champion,
    memory_cannot_mutate_ledger,
)
from src.python.memory import queries as mq
from src.python.memory.turso_conn import (
    TursoHttpConnection,
    connect_turso_backend,
    is_transient_error,
    sanitize_error,
)


def test_sqlite_write_local_not_remote(tmp_path):
    m = connect_sqlite(tmp_path / "a.db")
    w = mq.write_experiment(m, {
        "experiment_id": "E1", "fingerprint": "fp1", "status": "COMPLETED", "result_hash": "r",
    })
    assert w["persisted"] is True
    assert w["local_persisted"] is True
    assert w["remote_persisted"] is False
    assert w["backend"] in ("sqlite", "sqlite_fallback")


def test_unavailable_write_both_false():
    m = ResearchMemory(status=MemoryStatus.UNAVAILABLE)
    w = mq.write_experiment(m, {"experiment_id": "X", "fingerprint": "Y"})
    assert w["status"] == "MEMORY_UNAVAILABLE"
    assert w["persisted"] is False
    assert w["remote_persisted"] is False
    assert w["local_persisted"] is False


def test_no_match_vs_unavailable(tmp_path):
    m = connect_sqlite(tmp_path / "b.db")
    assert mq.query_by_fingerprint(m, "none")["status"] == "NO_MATCH"
    u = ResearchMemory(status=MemoryStatus.UNAVAILABLE)
    assert mq.query_by_fingerprint(u, "none")["status"] == "MEMORY_UNAVAILABLE"


def test_domain_query_apis(tmp_path):
    m = connect_sqlite(tmp_path / "c.db")
    assert mq.write_hypothesis(m, {"hypothesis_id": "H1", "hypothesis": "x", "status": "OPEN"})["persisted"]
    assert mq.query_hypotheses(m, "H1")["status"] == "MATCH_FOUND"
    assert mq.query_hypotheses(m, "NOPE")["status"] == "NO_MATCH"
    assert mq.write_failure(m, {"failure_id": "F1", "failure_type": "SL"})["persisted"]
    assert mq.query_failures(m, "F1")["match"]
    assert mq.write_knowledge(m, {"knowledge_id": "K1", "source_type": "HUMAN_NOTE", "content": "n"})["persisted"]
    assert mq.query_knowledge(m, "K1")["match"]
    assert mq.write_drift(m, {"drift_id": "D1", "metric": "sharpe"})["persisted"]
    assert mq.query_drift(m, "D1")["match"]


def test_schema_v2_migration_idempotent(tmp_path):
    db = tmp_path / "m2.db"
    m1 = connect_sqlite(db)
    m2 = connect_sqlite(db)
    w = mq.write_experiment(m1, {
        "experiment_id": "E3", "fingerprint": "fp3", "status": "OK",
        "artifact_reference": "drive://x", "dependency_snapshot": {"data": "AVAILABLE"},
    })
    assert w["persisted"] is True
    m1.close(); m2.close()


def test_http_status_codes():
    codes = {
        401: "AUTH_ERROR", 403: "AUTH_ERROR", 400: "http_400", 404: "http_404",
        429: "429", 500: "server_500", 502: "server_502", 503: "server_503", 504: "server_504",
    }
    for code, expect in codes.items():
        mock_resp = MagicMock()
        mock_resp.status_code = code
        mock_resp.json.return_value = {}
        with patch("httpx.Client") as client_cls:
            client = MagicMock()
            client.__enter__ = MagicMock(return_value=client)
            client.__exit__ = MagicMock(return_value=False)
            client.post.return_value = mock_resp
            client_cls.return_value = client
            conn, backend, err = connect_turso_backend(
                "libsql://t.turso.io", "tok", prefer_http=True, max_attempts=1,
            )
        assert conn is None
        assert err == expect, (code, err, expect)


def test_http_malformed_and_sql_error():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("bad")
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.return_value = mock_resp
        client_cls.return_value = client
        _, _, err = connect_turso_backend("libsql://t.turso.io", "tok", prefer_http=True, max_attempts=1)
    assert err == "malformed_json"

    mock_resp2 = MagicMock()
    mock_resp2.status_code = 200
    mock_resp2.json.return_value = {"results": [{"type": "error", "error": {"message": "no such table"}}]}
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.return_value = mock_resp2
        client_cls.return_value = client
        _, _, err = connect_turso_backend("libsql://t.turso.io", "tok", prefer_http=True, max_attempts=1)
    assert "sql_error" in err or "no such" in err.lower()


def test_http_missing_results():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {}
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.return_value = mock_resp
        client_cls.return_value = client
        _, _, err = connect_turso_backend("libsql://t.turso.io", "tok", prefer_http=True, max_attempts=1)
    assert err == "missing_results"


def test_bounded_retry_transient_then_success():
    calls = {"n": 0}
    def post_side_effect(*a, **k):
        calls["n"] += 1
        r = MagicMock()
        if calls["n"] < 2:
            r.status_code = 503
            r.json.return_value = {}
        else:
            r.status_code = 200
            r.json.return_value = {"results": [{"type": "ok", "response": {"result": {
                "cols": [{"name": "x"}], "rows": [[{"type": "integer", "value": "1"}]],
            }}}]}
        return r
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.side_effect = post_side_effect
        client_cls.return_value = client
        conn = TursoHttpConnection(database_url="libsql://t.turso.io", auth_token="tok", max_attempts=3, backoff_sec=0.0)
        assert conn.execute("SELECT 1").fetchall()
    assert calls["n"] == 2


def test_no_retry_on_auth():
    calls = {"n": 0}
    def post_side_effect(*a, **k):
        calls["n"] += 1
        r = MagicMock()
        r.status_code = 401
        r.json.return_value = {}
        return r
    with patch("httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__ = MagicMock(return_value=client)
        client.__exit__ = MagicMock(return_value=False)
        client.post.side_effect = post_side_effect
        client_cls.return_value = client
        conn = TursoHttpConnection(database_url="libsql://t.turso.io", auth_token="bad", max_attempts=5, backoff_sec=0.0)
        with pytest.raises(RuntimeError):
            conn.execute("SELECT 1")
    assert calls["n"] == 1


def test_sanitize_and_isolation():
    assert "SECRETTOKEN" not in sanitize_error("Bearer SECRETTOKEN abc")
    assert is_transient_error("TIMEOUT") is True
    assert is_transient_error("AUTH_ERROR") is False
    assert memory_cannot_mutate_ledger() is True
    assert memory_cannot_mutate_champion() is True
    assert memory_cannot_approve_evidence() is True


def test_idempotent_retry_one_record(tmp_path):
    m = connect_sqlite(tmp_path / "id.db")
    row = {"experiment_id": "EX", "fingerprint": "same", "status": "DONE"}
    w1 = mq.write_experiment(m, row)
    w2 = mq.write_experiment(m, row)
    assert w1["persisted"] and w2["idempotent"]
    assert len(m.list_recent_experiments()) == 1
