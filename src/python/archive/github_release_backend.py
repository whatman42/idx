"""GitHub Releases cold-archive backend (GitHub Free compatible).

Uses GITHUB_TOKEN from environment only. Never logs tokens.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from src.python.archive.integrity import sha256_bytes


class GitHubReleaseArchiveBackend:
    name = "github_release"
    API = "https://api.github.com"

    def __init__(
        self,
        *,
        owner: str = "",
        repo: str = "",
        token: str = "",
        timeout_sec: float = 60.0,
    ) -> None:
        self.owner = owner or os.environ.get("GITHUB_REPOSITORY_OWNER", "") or os.environ.get(
            "GITHUB_OWNER", "whatman42"
        )
        repo_full = os.environ.get("GITHUB_REPOSITORY", "")
        if not repo and repo_full and "/" in repo_full:
            self.owner, self.repo = repo_full.split("/", 1)
        else:
            self.repo = repo or os.environ.get("GITHUB_REPO", "idx")
        self.token = token or os.environ.get("GITHUB_TOKEN", "") or os.environ.get("GH_TOKEN", "")
        self.timeout_sec = timeout_sec
        self.last_error = ""

    def available(self) -> bool:
        return bool(self.token and self.owner and self.repo)

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise RuntimeError("AUTH_FAILED")
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(
        self, method: str, path: str, *, json_body: Any = None, data: bytes | None = None, extra_headers: dict | None = None
    ) -> tuple[int, Any]:
        import httpx

        url = path if path.startswith("http") else f"{self.API}{path}"
        hdrs = {**self._headers(), **(extra_headers or {})}
        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                resp = client.request(method, url, json=json_body, content=data, headers=hdrs)
        except Exception as e:
            raise RuntimeError(f"network_{type(e).__name__}") from e
        if resp.status_code in (401, 403):
            raise RuntimeError("AUTH_FAILED" if resp.status_code == 401 else "PERMISSION_DENIED")
        if resp.status_code == 404:
            return 404, {}
        if resp.status_code >= 400:
            raise RuntimeError(f"http_{resp.status_code}")
        try:
            body = resp.json() if resp.content else {}
        except Exception:
            body = {}
        return resp.status_code, body

    def ensure_release(self, tag: str, *, name: str = "", body: str = "") -> dict:
        code, data = self._request("GET", f"/repos/{self.owner}/{self.repo}/releases/tags/{tag}")
        if code == 200 and data.get("id"):
            return data
        code, data = self._request(
            "POST",
            f"/repos/{self.owner}/{self.repo}/releases",
            json_body={
                "tag_name": tag,
                "name": name or tag,
                "body": body or "IDX cold archive release",
                "draft": False,
                "prerelease": False,
            },
        )
        if not data.get("id"):
            raise RuntimeError("RELEASE_CREATE_FAILED")
        return data

    def list_assets(self, release_id: int) -> list[dict]:
        _, data = self._request("GET", f"/repos/{self.owner}/{self.repo}/releases/{release_id}/assets")
        return data if isinstance(data, list) else []

    def put(
        self,
        *,
        identity: str,
        artifact_id: str,
        content_sha256: str,
        archive_bytes: bytes,
        archive_sha256: str,
        meta: dict,
        folder_key: str,
        release_tag: str,
        asset_name: str,
    ) -> dict:
        if not self.available():
            raise RuntimeError("CONFIG_ERROR")
        release = self.ensure_release(release_tag)
        release_id = int(release["id"])
        assets = self.list_assets(release_id)
        for a in assets:
            if a.get("name") == asset_name:
                return {
                    "identity": identity,
                    "artifact_id": artifact_id,
                    "content_sha256": content_sha256,
                    "archive_sha256": archive_sha256,
                    "size_bytes": len(archive_bytes),
                    "file_id": str(a.get("id")),
                    "release_id": release_id,
                    "release_tag": release_tag,
                    "asset_name": asset_name,
                    "idempotent": True,
                    "status": "ARCHIVE_ALREADY_PRESENT",
                    "meta": meta,
                }
        prefix = f"{artifact_id.replace('/', '_')}_"
        for a in assets:
            n = a.get("name") or ""
            if n.startswith(prefix) and n.endswith(".tar.gz") and n != asset_name:
                return {
                    "status": "ARCHIVE_CONFLICT",
                    "artifact_id": artifact_id,
                    "existing_asset": n,
                    "idempotent": False,
                }
        upload_url = release.get("upload_url", "").split("{")[0]
        if not upload_url:
            raise RuntimeError("NO_UPLOAD_URL")
        import httpx

        hdrs = {**self._headers(), "Content-Type": "application/gzip"}
        url = f"{upload_url}?name={asset_name}"
        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                resp = client.post(url, content=archive_bytes, headers=hdrs)
        except Exception as e:
            raise RuntimeError(f"network_{type(e).__name__}") from e
        if resp.status_code in (401, 403):
            raise RuntimeError("AUTH_FAILED" if resp.status_code == 401 else "PERMISSION_DENIED")
        if resp.status_code >= 400:
            raise RuntimeError(f"http_{resp.status_code}")
        created = resp.json()
        sha_name = asset_name + ".sha256"
        sha_body = f"{archive_sha256}  {asset_name}\n".encode()
        try:
            with httpx.Client(timeout=self.timeout_sec) as client:
                client.post(
                    f"{upload_url}?name={sha_name}",
                    content=sha_body,
                    headers={**self._headers(), "Content-Type": "text/plain"},
                )
        except Exception:
            pass
        return {
            "identity": identity,
            "artifact_id": artifact_id,
            "content_sha256": content_sha256,
            "archive_sha256": archive_sha256,
            "size_bytes": len(archive_bytes),
            "file_id": str(created.get("id")),
            "release_id": release_id,
            "release_tag": release_tag,
            "asset_name": asset_name,
            "idempotent": False,
            "status": "ARCHIVE_SUCCESS",
            "meta": meta,
        }

    def get(self, *, file_id: str = "", identity: str = "", download_url: str = "") -> Optional[tuple[bytes, dict]]:
        if not download_url and not file_id:
            return None
        import httpx

        url = download_url
        if not url and file_id:
            url = f"{self.API}/repos/{self.owner}/{self.repo}/releases/assets/{file_id}"
        hdrs = {**self._headers(), "Accept": "application/octet-stream"}
        try:
            with httpx.Client(timeout=self.timeout_sec, follow_redirects=True) as client:
                resp = client.get(url, headers=hdrs)
        except Exception as e:
            raise RuntimeError(f"network_{type(e).__name__}") from e
        if resp.status_code == 404:
            return None
        if resp.status_code in (401, 403):
            raise RuntimeError("AUTH_FAILED" if resp.status_code == 401 else "PERMISSION_DENIED")
        if resp.status_code >= 400:
            raise RuntimeError(f"http_{resp.status_code}")
        data = resp.content
        return data, {
            "file_id": file_id,
            "archive_sha256": sha256_bytes(data),
            "size_bytes": len(data),
            "download_url": url,
        }
