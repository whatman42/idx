"""Google Drive cold-archive backend (optional).

Auth via GDRIVE_SERVICE_ACCOUNT_JSON or GDRIVE_SERVICE_ACCOUNT_FILE.
Scope: drive.file. Never logs credentials.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Optional

from src.python.archive.contracts import DRIVE_COLD_FOLDER_NAME, DRIVE_ROOT_FOLDER_NAME
from src.python.archive.integrity import sha256_bytes


def _sanitize(msg: str) -> str:
    s = str(msg or "")[:200]
    low = s.lower()
    for m in ("bearer ", "private_key", "client_secret", "refresh_token", "token="):
        if m in low:
            return "CREDENTIAL_REDACTED"
    return s


class GoogleDriveBackend:
    name = "gdrive"
    SCOPE = "https://www.googleapis.com/auth/drive.file"

    def __init__(
        self,
        *,
        timeout_sec: float = 30.0,
        max_attempts: int = 3,
        service_account_info: Optional[dict] = None,
    ) -> None:
        self.timeout_sec = timeout_sec
        self.max_attempts = max_attempts
        self._creds = None
        self._folder_cache: dict[str, str] = {}
        self.last_error = ""
        self._service_account_info = service_account_info

    @classmethod
    def from_env(cls) -> "GoogleDriveBackend":
        info = None
        raw = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON", "").strip()
        path = os.environ.get("GDRIVE_SERVICE_ACCOUNT_FILE", "").strip()
        if raw:
            try:
                info = json.loads(raw)
            except Exception as e:
                b = cls()
                b.last_error = f"CONFIG_ERROR:{type(e).__name__}"
                return b
        elif path and os.path.isfile(path):
            try:
                info = json.loads(open(path, encoding="utf-8").read())
            except Exception as e:
                b = cls()
                b.last_error = f"CONFIG_ERROR:{type(e).__name__}"
                return b
        return cls(service_account_info=info)

    def available(self) -> bool:
        return self._ensure_creds() is not None

    def _ensure_creds(self) -> Any:
        if self._creds is not None:
            return self._creds
        if not self._service_account_info:
            self.last_error = "CONFIG_ERROR"
            return None
        try:
            from google.oauth2 import service_account  # type: ignore
            from google.auth.transport.requests import Request  # type: ignore
        except ImportError:
            self.last_error = "google_auth_missing"
            return None
        try:
            creds = service_account.Credentials.from_service_account_info(
                self._service_account_info, scopes=[self.SCOPE]
            )
            creds.refresh(Request())
            self._creds = creds
            return self._creds
        except Exception as e:
            self.last_error = _sanitize(f"AUTH:{type(e).__name__}")
            return None

    def _headers(self) -> dict[str, str]:
        creds = self._ensure_creds()
        if creds is None:
            raise RuntimeError(self.last_error or "AUTH_FAILED")
        return {"Authorization": f"Bearer {creds.token}"}

    def _request(
        self, method: str, url: str, *, params=None, json_body=None, headers=None, content=None
    ) -> tuple[int, Any]:
        import httpx

        hdrs = {**self._headers(), **(headers or {})}
        last_err = ""
        for attempt in range(max(1, self.max_attempts)):
            try:
                with httpx.Client(timeout=self.timeout_sec) as client:
                    resp = client.request(
                        method, url, params=params, json=json_body, content=content, headers=hdrs
                    )
            except Exception as e:
                last_err = f"network_{type(e).__name__}"
                if attempt + 1 >= self.max_attempts:
                    raise RuntimeError(last_err)
                time.sleep(0.05 * (attempt + 1))
                continue
            code = resp.status_code
            if code in (401, 403):
                raise RuntimeError("AUTH_FAILED" if code == 401 else "PERMISSION_DENIED")
            if code == 429 or code >= 500:
                last_err = f"http_{code}"
                if attempt + 1 >= self.max_attempts:
                    raise RuntimeError(last_err)
                time.sleep(0.05 * (attempt + 1))
                continue
            if code == 404:
                raise RuntimeError("NOT_FOUND")
            if code >= 400:
                raise RuntimeError(f"http_{code}")
            try:
                body = resp.json() if resp.content else {}
            except Exception:
                body = {}
            return code, body
        raise RuntimeError(last_err or "UNAVAILABLE")

    def ensure_folder(self, name: str, parent_id: Optional[str] = None) -> str:
        cache_key = f"{parent_id or 'root'}:{name}"
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]
        q = (
            f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        if parent_id:
            q += f" and '{parent_id}' in parents"
        _, body = self._request(
            "GET",
            "https://www.googleapis.com/drive/v3/files",
            params={"q": q, "spaces": "drive", "fields": "files(id,name)"},
        )
        files = body.get("files") or []
        if files:
            fid = files[0]["id"]
            self._folder_cache[cache_key] = fid
            return fid
        meta: dict[str, Any] = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            meta["parents"] = [parent_id]
        _, created = self._request(
            "POST",
            "https://www.googleapis.com/drive/v3/files",
            json_body=meta,
            params={"fields": "id"},
        )
        fid = created["id"]
        self._folder_cache[cache_key] = fid
        return fid

    def ensure_cold_tree(self, category: str) -> str:
        root = self.ensure_folder(DRIVE_ROOT_FOLDER_NAME)
        cold = self.ensure_folder(DRIVE_COLD_FOLDER_NAME, root)
        return self.ensure_folder(category, cold)

    def put(
        self, *, logical_id: str, data: bytes, content_hash: str, meta: dict, folder_key: str
    ) -> dict:
        folder_id = self.ensure_cold_tree(folder_key)
        q = (
            f"name='{content_hash[:16]}_{logical_id.replace('/', '_')[:80]}' "
            f"and '{folder_id}' in parents and trashed=false"
        )
        _, existing = self._request(
            "GET",
            "https://www.googleapis.com/drive/v3/files",
            params={"q": q, "fields": "files(id,name)"},
        )
        files = existing.get("files") or []
        if files:
            return {
                "logical_id": logical_id,
                "content_hash": content_hash,
                "size_bytes": len(data),
                "file_id": files[0]["id"],
                "folder_id": folder_id,
                "folder_key": folder_key,
                "meta": meta,
                "idempotent": True,
            }
        import httpx

        boundary = "idx_archive_boundary"
        metadata = {
            "name": f"{content_hash[:16]}_{logical_id.replace('/', '_')[:80]}",
            "parents": [folder_id],
            "appProperties": {
                "content_hash": content_hash,
                "logical_id": logical_id[:100],
                "schema_version": str(meta.get("schema_version", 1)),
            },
        }
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            f"{json.dumps(metadata)}\r\n--{boundary}\r\n"
            f"Content-Type: application/octet-stream\r\n\r\n"
        ).encode("utf-8") + data + f"\r\n--{boundary}--".encode("utf-8")
        hdrs = {**self._headers(), "Content-Type": f"multipart/related; boundary={boundary}"}
        last_err = ""
        for attempt in range(max(1, self.max_attempts)):
            try:
                with httpx.Client(timeout=self.timeout_sec) as client:
                    resp = client.post(
                        "https://www.googleapis.com/upload/drive/v3/files",
                        params={"uploadType": "multipart", "fields": "id,name,size"},
                        content=body,
                        headers=hdrs,
                    )
            except Exception as e:
                last_err = f"network_{type(e).__name__}"
                if attempt + 1 >= self.max_attempts:
                    raise RuntimeError(last_err)
                time.sleep(0.05 * (attempt + 1))
                continue
            if resp.status_code in (401, 403):
                raise RuntimeError("AUTH_FAILED" if resp.status_code == 401 else "PERMISSION_DENIED")
            if resp.status_code == 429 or resp.status_code >= 500:
                last_err = f"http_{resp.status_code}"
                if attempt + 1 >= self.max_attempts:
                    raise RuntimeError(last_err)
                time.sleep(0.05 * (attempt + 1))
                continue
            if resp.status_code >= 400:
                raise RuntimeError(f"http_{resp.status_code}")
            created = resp.json()
            return {
                "logical_id": logical_id,
                "content_hash": content_hash,
                "size_bytes": len(data),
                "file_id": created["id"],
                "folder_id": folder_id,
                "folder_key": folder_key,
                "meta": meta,
                "idempotent": False,
            }
        raise RuntimeError(last_err or "UPLOAD_FAILED")

    def get(self, *, file_id: str = "", logical_id: str = "") -> Optional[tuple[bytes, dict]]:
        if not file_id:
            return None
        import httpx

        hdrs = self._headers()
        with httpx.Client(timeout=self.timeout_sec) as client:
            meta_resp = client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params={"fields": "id,name,size,appProperties"},
                headers=hdrs,
            )
            if meta_resp.status_code == 404:
                return None
            if meta_resp.status_code in (401, 403):
                raise RuntimeError(
                    "AUTH_FAILED" if meta_resp.status_code == 401 else "PERMISSION_DENIED"
                )
            if meta_resp.status_code >= 400:
                raise RuntimeError(f"http_{meta_resp.status_code}")
            meta = meta_resp.json()
            dl = client.get(
                f"https://www.googleapis.com/drive/v3/files/{file_id}",
                params={"alt": "media"},
                headers=hdrs,
            )
            if dl.status_code >= 400:
                raise RuntimeError(f"http_{dl.status_code}")
            data = dl.content
        app = meta.get("appProperties") or {}
        expected = app.get("content_hash") or ""
        if expected and sha256_bytes(data) != expected:
            raise ValueError("ARCHIVE_INTEGRITY_FAILURE")
        return data, {
            "file_id": file_id,
            "content_hash": expected or sha256_bytes(data),
            "size_bytes": len(data),
            "meta": app,
            "logical_id": app.get("logical_id", logical_id),
        }
