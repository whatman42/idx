"""SHA-256 integrity and lightweight secret denylist for archive payloads."""
from __future__ import annotations

import hashlib
import re

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r'"private_key"\s*:'),
    re.compile(r"client_secret\s*[:=]", re.I),
    re.compile(r"refresh_token\s*[:=]", re.I),
    re.compile(r"access_token\s*[:=]", re.I),
    re.compile(r"TURSO_AUTH_TOKEN\s*[:=]", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I),
    re.compile(r"api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}", re.I),
]

DENY_NAME_FRAGMENTS = (
    "service_account.json",
    "credentials.json",
    "client_secret",
    ".pem",
    "id_rsa",
    ".env",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_secret_bytes(data: bytes, *, name: str = "") -> list[str]:
    hits: list[str] = []
    low_name = (name or "").lower()
    for frag in DENY_NAME_FRAGMENTS:
        if frag in low_name:
            hits.append(f"deny_name:{frag}")
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return hits
    sample = text[: 256 * 1024]
    for pat in SECRET_PATTERNS:
        if pat.search(sample):
            hits.append(f"pattern:{pat.pattern[:40]}")
    return hits


def assert_no_secrets(data: bytes, *, name: str = "") -> None:
    hits = scan_secret_bytes(data, name=name)
    if hits:
        raise ValueError(f"SECRET_DETECTED:{','.join(hits[:3])}")
