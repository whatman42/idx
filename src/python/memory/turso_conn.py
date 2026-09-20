"""Turso / libSQL connection backends for research memory.

Backends: libsql (optional) | HTTP /v2/pipeline via httpx
Never logs auth tokens. Never mutates Ledger / Champion / PromotionGate.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


def sanitize_error(msg: str) -> str:
    s = str(msg or "")[:300]
    low = s.lower()
    for marker in ("bearer ", "authorization:", "token=", "auth_token", "password="):
        if marker in low:
            return "CREDENTIAL_REDACTED"
    parts = []
    for tok in s.split():
        if len(tok) > 40 and any(c.isalnum() for c in tok):
            parts.append("[redacted]")
        else:
            parts.append(tok)
    return " ".join(parts)[:200]


def _normalize_http_url(url: str) -> str:
    u = (url or "").strip()
    if u.startswith("libsql://"):
        u = "https://" + u[len("libsql://") :]
    if u.startswith("http://"):
        u = "https://" + u[len("http://") :]
    return u.rstrip("/")


def _pipeline_url(db_url: str) -> str:
    base = _normalize_http_url(db_url)
    if base.endswith("/v2/pipeline"):
        return base
    return base + "/v2/pipeline"


def _encode_arg(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "null"}
    if isinstance(value, bool):
        return {"type": "integer", "value": "1" if value else "0"}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": str(value)}
    return {"type": "text", "value": str(value)}


TRANSIENT_MARKERS = frozenset({
    "TIMEOUT", "NETWORK", "network_", "timeout", "429", "500", "502", "503", "504",
    "server_500", "server_502", "server_503", "server_504",
})


def is_transient_error(err: str) -> bool:
    e = (err or "").lower()
    if "auth" in e or "401" in e or "403" in e or "400" in e or "config" in e:
        return False
    return any(m.lower() in e for m in TRANSIENT_MARKERS)


@dataclass
class TursoHttpConnection:
    database_url: str
    auth_token: str
    timeout_sec: float = 30.0
    max_attempts: int = 3
    backoff_sec: float = 0.05
    last_error: str = ""
    _closed: bool = False

    def execute(self, sql: str, params: Sequence[Any] = ()) -> "TursoCursor":
        if self._closed:
            raise RuntimeError("connection_closed")
        last_err = ""
        attempts = max(1, int(self.max_attempts))
        for i in range(attempts):
            rows, cols, err = self._pipeline_execute(sql, params)
            if not err:
                return TursoCursor(rows=rows, description=cols)
            last_err = err
            self.last_error = sanitize_error(err)
            if not is_transient_error(err) or i >= attempts - 1:
                break
            time.sleep(self.backoff_sec * (i + 1))
        raise RuntimeError(self.last_error or sanitize_error(last_err) or "execute_failed")

    def _pipeline_execute(
        self, sql: str, params: Sequence[Any]
    ) -> tuple[list[tuple], list[tuple], str]:
        try:
            import httpx
        except ImportError:
            return [], [], "httpx_missing"
        url = _pipeline_url(self.database_url)
        args = [_encode_arg(p) for p in params]
        body = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": args}},
                {"type": "close"},
            ]
        }
        headers = {
            "Authorization": f"Bearer {self.auth_token}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                resp = client.post(url, headers=headers, json=body)
        except Exception as e:
            name = type(e).__name__
            if "timeout" in name.lower() or "timeout" in str(e).lower():
                return [], [], "TIMEOUT"
            return [], [], f"network_{name}"
        code = resp.status_code
        if code in (401, 403):
            return [], [], "AUTH_ERROR"
        if code == 400:
            return [], [], "http_400"
        if code == 404:
            return [], [], "http_404"
        if code == 429:
            return [], [], "429"
        if code in (500, 502, 503, 504):
            return [], [], f"server_{code}"
        if code >= 400:
            return [], [], f"http_{code}"
        try:
            data = resp.json()
        except Exception:
            return [], [], "malformed_json"
        if not isinstance(data, dict):
            return [], [], "malformed_response"
        results = data.get("results")
        if results is None:
            return [], [], "missing_results"
        if not results:
            return [], [], "empty_pipeline_result"
        first = results[0]
        if not isinstance(first, dict):
            return [], [], "missing_results_0"
        if first.get("type") == "error" or first.get("error"):
            err = first.get("error") or first
            msg = err.get("message") if isinstance(err, dict) else str(err)
            return [], [], sanitize_error(f"sql_error:{msg}")
        response = first.get("response") or {}
        result = response.get("result") or {}
        cols_raw = result.get("cols") or []
        cols = [(c.get("name") if isinstance(c, dict) else str(c),) for c in cols_raw]
        rows_out: list[tuple] = []
        for row in result.get("rows") or []:
            values: list[Any] = []
            for cell in row:
                if not isinstance(cell, dict):
                    values.append(cell)
                    continue
                t = cell.get("type")
                if t == "null" or (cell.get("value") is None and t != "text"):
                    values.append(None)
                elif t in ("integer", "float"):
                    v = cell.get("value")
                    try:
                        values.append(int(v) if t == "integer" else float(v))
                    except (TypeError, ValueError):
                        values.append(v)
                else:
                    values.append(cell.get("value"))
            rows_out.append(tuple(values))
        return rows_out, cols, ""

    def commit(self) -> None:
        return None

    def close(self) -> None:
        self._closed = True

    def __repr__(self) -> str:
        return f"TursoHttpConnection(url={_normalize_http_url(self.database_url)!r}, token=***)"


@dataclass
class TursoCursor:
    rows: list[tuple] = field(default_factory=list)
    description: list[tuple] = field(default_factory=list)

    def fetchall(self) -> list[tuple]:
        return list(self.rows)

    def fetchone(self) -> Optional[tuple]:
        return self.rows[0] if self.rows else None


@dataclass
class LibsqlConnectionAdapter:
    _conn: Any

    def execute(self, sql: str, params: Sequence[Any] = ()) -> Any:
        return self._conn.execute(sql, tuple(params) if params else ())

    def commit(self) -> None:
        if hasattr(self._conn, "commit"):
            self._conn.commit()

    def close(self) -> None:
        if hasattr(self._conn, "close"):
            self._conn.close()

    def __repr__(self) -> str:
        return "LibsqlConnectionAdapter(token=***)"


def try_connect_libsql(url: str, token: str) -> tuple[Optional[Any], str]:
    try:
        import libsql  # type: ignore
    except ImportError:
        return None, "libsql_package_missing"
    try:
        conn = libsql.connect(database=url, auth_token=token)
        conn.execute("SELECT 1")
        if hasattr(conn, "commit"):
            try:
                conn.commit()
            except Exception:
                pass
        return LibsqlConnectionAdapter(_conn=conn), ""
    except Exception as e:
        return None, sanitize_error(f"libsql_{type(e).__name__}")


def try_connect_http(
    url: str, token: str, *, timeout_sec: float = 30.0, max_attempts: int = 3
) -> tuple[Optional[TursoHttpConnection], str]:
    if not url or not token:
        return None, "CONFIG_ERROR"
    conn = TursoHttpConnection(
        database_url=url, auth_token=token, timeout_sec=timeout_sec, max_attempts=max_attempts
    )
    try:
        cur = conn.execute("SELECT 1")
        _ = cur.fetchall()
        return conn, ""
    except Exception as e:
        err = conn.last_error or sanitize_error(type(e).__name__)
        return None, err


def connect_turso_backend(
    url: str,
    token: str,
    *,
    timeout_sec: float = 30.0,
    prefer_http: bool = False,
    max_attempts: int = 3,
) -> tuple[Optional[Any], str, str]:
    url = (url or "").strip()
    token = (token or "").strip()
    if not url or not token:
        return None, "none", "CONFIG_ERROR"
    if not prefer_http:
        conn, err = try_connect_libsql(url, token)
        if conn is not None:
            return conn, "libsql", ""
    conn_h, err_h = try_connect_http(
        url, token, timeout_sec=timeout_sec, max_attempts=max_attempts
    )
    if conn_h is not None:
        return conn_h, "http", ""
    if prefer_http:
        conn, err = try_connect_libsql(url, token)
        if conn is not None:
            return conn, "libsql", ""
        return None, "none", err_h or err
    return None, "none", err_h or "UNAVAILABLE"
