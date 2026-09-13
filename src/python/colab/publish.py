"""Optional publish of candidate artifacts to GitHub — never force-push, never touch production pointer.

Uses GH_PAT from environment / Colab secrets. Never logs the token.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional


def _token() -> Optional[str]:
    t = (os.getenv("GH_PAT") or os.getenv("GITHUB_TOKEN") or "").strip()
    return t or None


def publish_candidates(
    *,
    owner: str = "whatman42",
    repo: str = "idx",
    branch: str = "main",
    paths: Optional[list[str]] = None,
    commit_message: str = "chore(colab): publish training candidates (no production change)",
) -> dict[str, Any]:
    token = _token()
    if not token:
        return {
            "status": "SKIPPED",
            "reason": "GH_PAT_absent",
            "published": [],
            "token_present": False,
            "production_pointer_touched": False,
            "force_push": False,
        }

    paths = paths or [
        "artifacts/training/last_training_report.json",
        "artifacts/training/shadow_report.json",
    ]
    published = []
    errors = []
    for rel in paths:
        p = Path(rel)
        if not p.exists() or not p.is_file():
            continue
        if p.suffix in {".env", ".pem", ".key"}:
            errors.append({"path": rel, "error": "blocked_secret_extension"})
            continue
        try:
            content = p.read_bytes()
            b64 = base64.b64encode(content).decode("ascii")
            api = f"https://api.github.com/repos/{owner}/{repo}/contents/{rel}"
            req_get = urllib.request.Request(api + f"?ref={branch}", method="GET")
            req_get.add_header("Authorization", f"Bearer {token}")
            req_get.add_header("Accept", "application/vnd.github+json")
            sha = None
            try:
                with urllib.request.urlopen(req_get, timeout=30) as resp:
                    meta = json.loads(resp.read().decode())
                    sha = meta.get("sha")
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    raise
            body = {"message": commit_message, "content": b64, "branch": branch}
            if sha:
                body["sha"] = sha
            data = json.dumps(body).encode()
            req = urllib.request.Request(api, data=data, method="PUT")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("Accept", "application/vnd.github+json")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode())
            published.append({"path": rel, "commit": (result.get("commit") or {}).get("sha", "")[:40]})
        except Exception as e:
            errors.append({"path": rel, "error": f"{type(e).__name__}"})

    return {
        "status": "OK" if published and not errors else ("PARTIAL" if published else "FAILED"),
        "published": published,
        "errors": errors,
        "token_present": True,
        "production_pointer_touched": False,
        "force_push": False,
    }
