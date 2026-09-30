"""Crypto OHLCV / universe quality checks — fail-closed helpers."""
from __future__ import annotations

from typing import Any

import pandas as pd

from src.python.crypto.config import CRYPTO_MIN_HISTORY_BARS, assert_crypto_paper_only


def validate_ohlcv_frame(df: pd.DataFrame, *, symbol: str = "") -> dict[str, Any]:
    assert_crypto_paper_only()
    issues: list[str] = []
    if df is None or df.empty:
        return {"ok": False, "issues": ["EMPTY"], "symbol": symbol, "n_bars": 0}
    need = {"timestamp", "open", "high", "low", "close"}
    missing = need - set(df.columns)
    if missing:
        issues.append(f"MISSING_COLS:{sorted(missing)}")
    n = len(df)
    if n < CRYPTO_MIN_HISTORY_BARS:
        issues.append(f"INSUFFICIENT_HISTORY:{n}<{CRYPTO_MIN_HISTORY_BARS}")
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        if ts.isna().any():
            issues.append("MALFORMED_TIMESTAMP")
        if not ts.is_monotonic_increasing:
            issues.append("TIMESTAMP_NOT_ORDERED")
        if ts.duplicated().any():
            issues.append("DUPLICATE_TIMESTAMP")
    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            if s.isna().any() or (s <= 0).any():
                issues.append(f"INVALID_{col.upper()}")
    if all(c in df.columns for c in ("open", "high", "low", "close")):
        o = pd.to_numeric(df["open"], errors="coerce")
        h = pd.to_numeric(df["high"], errors="coerce")
        l = pd.to_numeric(df["low"], errors="coerce")
        c = pd.to_numeric(df["close"], errors="coerce")
        if ((h < l) | (h < o) | (h < c) | (l > o) | (l > c)).any():
            issues.append("IMPOSSIBLE_OHLC")
    return {"ok": len(issues) == 0, "issues": issues, "symbol": symbol, "n_bars": n}


def coverage_report(**counts: Any) -> dict[str, Any]:
    return {"plane": "CRYPTO", "coverage": dict(counts), "silent_drop": False}
