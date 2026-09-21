"""Stale market-structure metadata → fail-closed."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.python.market_structure.models import MarketStructureSnapshot


def parse_ts(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def is_stale(
    snapshot: MarketStructureSnapshot,
    *,
    now: Optional[datetime] = None,
    max_age_seconds: float = 86_400.0,
) -> bool:
    ts = parse_ts(snapshot.as_of)
    if ts is None:
        return True
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    ref = now or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    age = (ref - ts).total_seconds()
    return age < 0 or age > max_age_seconds
