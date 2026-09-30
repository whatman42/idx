"""Crypto cycle identity — operational provenance."""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone


def new_cycle_id(*, prefix: str = "CRYPTO") -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{ts}-{uuid.uuid4().hex[:8].upper()}"


def deterministic_cycle_id(*, seed: str) -> str:
    h = hashlib.sha256(seed.encode()).hexdigest()[:12].upper()
    return f"CRYPTO-DET-{h}"
