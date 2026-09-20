"""SHA-256, secret denylist, tar.gz compression for cold archives."""
from __future__ import annotations

import hashlib
import io
import re
import tarfile
from pathlib import Path
from typing import Mapping

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r'"private_key"\s*:'),
    re.compile(r"client_secret\s*[:=]", re.I),
    re.compile(r"refresh_token\s*[:=]", re.I),
    re.compile(r"access_token\s*[:=]", re.I),
    re.compile(r"TURSO_AUTH_TOKEN\s*[:=]", re.I),
    re.compile(r"GDRIVE_", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*", re.I),
    re.compile(r"api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}", re.I),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
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


def sha256_file(path: str | Path) -> str:
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


def make_tar_gz(files: Mapping[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in sorted(files.keys()):
            payload = files[name]
            assert_no_secrets(payload, name=name)
            info = tarfile.TarInfo(name=name)
            info.size = len(payload)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            tar.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


def extract_tar_gz(data: bytes) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for m in tar.getmembers():
            if not m.isfile():
                continue
            f = tar.extractfile(m)
            if f is None:
                continue
            out[m.name] = f.read()
    return out
