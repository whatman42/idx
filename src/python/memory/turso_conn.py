"""Turso / libSQL connection backends for research memory.

Backends (preference order when TURSO_* env is set):
  1. libsql Python package (official remote)
  2. HTTP /v2/pipeline via httpx (no native deps; uses existing httpx)

Never logs auth tokens.
Never mutates Ledger / Champion / PromotionGate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence


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


@dataclass
class TursoHttpConnection:
    database_url: str
    auth_token: str
    timeout_sec: float = 30.0
    last_error: str = ""
    _closed: bool = False

    def execute(self, sql: str, params: Sequence[Any] = ()) -> "TursoCursor":
        if self._closed:
            raise RuntimeError("connection_closed")
        rows, cols, err = self._pipeline_execute(sql, params)
        if err:
            self.last_error = err
            raise RuntimeError(err)
        return TursoCursor(rows=rows, description=cols)

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
            return [], [], f"network_{type(e).__name__}"

        if resp.status_code in (401, 403):
            return [], [], "AUTH_ERROR"
        if resp.status_code >= 500:
            return [], [], f"server_{resp.status_code}"
        if resp.status_code >= 400:
            return [], [], f"http_{resp.status_code}"

        try:
            data = resp.json()
        except Exception:
            return [], [], "invalid_json"

        results = data.get("results") or []
        if not results:
            return [], [], "empty_pipeline_result"

        first = results[0]
        if first.get("type") == "error" or first.get("error"):
            err = first.get("error") or first
            msg = err.get("message") if isinstance(err, dict) else str(err)
            return [], [], f"sql_error:{msg}"[:200]

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
        cur = self._conn.execute(sql, tuple(params) if params else ())
        return cur

    def commit(self) -> None:
        if hasattr(self._conn, "commit"):
            self._conn.commit()

    def close(self) -> None:
        if hasattr(self._conn, "close"):
            self._conn.close()


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
        return None, f"libsql_{type(e).__name__}"


def try_connect_http(
    url: str, token: str, *, timeout_sec: float = 30.0
) -> tuple[Optional[TursoHttpConnection], str]:
    if not url or not token:
        return None, "CONFIG_ERROR"
    conn = TursoHttpConnection(database_url=url, auth_token=token, timeout_sec=timeout_sec)
    try:
        cur = conn.execute("SELECT 1")
        _ = cur.fetchall()
        return conn, ""
    except Exception as e:
        err = conn.last_error or type(e).__name__
        return None, err


def connect_turso_backend(
    url: str,
    token: str,
    *,
    timeout_sec: float = 30.0,
    prefer_http: bool = False,
) -> tuple[Optional[Any], str, str]:
    url = (url or "").strip()
    token = (token or "").strip()
    if not url or not token:
        return None, "none", "CONFIG_ERROR"

    if not prefer_http:
        conn, err = try_connect_libsql(url, token)
        if conn is not None:
            return conn, "libsql", ""

    conn_h, err_h = try_connect_http(url, token, timeout_sec=timeout_sec)
    if conn_h is not None:
        return conn_h, "http", ""

    if prefer_http:
        conn, err = try_connect_libsql(url, token)
        if conn is not None:
            return conn, "libsql", ""
        return None, "none", err_h or err

    return None, "none", err_h or "UNAVAILABLE"
