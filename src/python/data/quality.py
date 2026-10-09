"""OHLCV data quality contracts — fail-closed, no silent cleaning.

Invalid data → QualityReport(ok=False). Callers must NOT emit signals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd


@dataclass
class QualityReport:
    ok: bool = True
    issues: list[str] = field(default_factory=list)
    symbols_expected: int = 0
    symbols_received: int = 0
    symbols_valid: int = 0
    symbols_invalid: int = 0
    symbols_missing: int = 0
    coverage_ratio: float = 0.0
    rows: int = 0
    status: str = "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "issues": list(self.issues),
            "symbols_expected": self.symbols_expected,
            "symbols_received": self.symbols_received,
            "symbols_valid": self.symbols_valid,
            "symbols_invalid": self.symbols_invalid,
            "symbols_missing": self.symbols_missing,
            "coverage_ratio": self.coverage_ratio,
            "rows": self.rows,
        }


REQUIRED_COLS = ("timestamp", "symbol", "open", "high", "low", "close", "volume")


def validate_ohlcv(
    df: pd.DataFrame,
    *,
    max_gap_days: float = 45.0,
    expected_symbols: Optional[list[str]] = None,
    min_coverage: float = 0.0,
    now: Optional[datetime] = None,
    allow_future: bool = False,
) -> QualityReport:
    """Validate OHLCV frame. Never mutates input. Never forward-fills."""
    issues: list[str] = []
    if df is None or getattr(df, "empty", True):
        return QualityReport(
            ok=False,
            issues=["empty_frame"],
            status="DATA_UNAVAILABLE",
            symbols_expected=len(expected_symbols or []),
            symbols_missing=len(expected_symbols or []),
        )

    report = QualityReport(rows=len(df))
    cols = set(df.columns)
    missing = set(REQUIRED_COLS) - cols
    if missing:
        issues.append(f"missing_cols:{sorted(missing)}")
        report.ok = False
        report.issues = issues
        report.status = "INVALID_SCHEMA"
        return report

    work = df.copy()
    ts = pd.to_datetime(work["timestamp"], errors="coerce", utc=True)
    if ts.isna().any():
        issues.append("bad_timestamps")
    n_now = now or datetime.now(timezone.utc)
    if n_now.tzinfo is None:
        n_now = n_now.replace(tzinfo=timezone.utc)
    if not allow_future and (ts.dropna() > pd.Timestamp(n_now)).any():
        issues.append("future_timestamps")

    for col in ("open", "high", "low", "close", "volume"):
        s = pd.to_numeric(work[col], errors="coerce")
        if s.isna().any():
            issues.append(f"missing_value:{col}")
        if (s.dropna() < 0).any():
            issues.append(f"negative:{col}")

    o = pd.to_numeric(work["open"], errors="coerce")
    h = pd.to_numeric(work["high"], errors="coerce")
    l = pd.to_numeric(work["low"], errors="coerce")
    c = pd.to_numeric(work["close"], errors="coerce")
    if ((h < o) | (h < c) | (h < l)).fillna(False).any():
        issues.append("high_lt_components")
    if ((l > o) | (l > c) | (l > h)).fillna(False).any():
        issues.append("low_gt_components")
    if (c.dropna() <= 0).any():
        issues.append("invalid_close")

    work = work.copy()
    work["timestamp"] = ts
    syms = work["symbol"].astype(str)
    report.symbols_received = int(syms.nunique())
    invalid_syms = 0
    for sym, g in work.groupby(syms, sort=False):
        gts = g["timestamp"].dropna().sort_values()
        if gts.duplicated().any():
            issues.append(f"duplicate_candle:{sym}")
            invalid_syms += 1
        if len(gts) >= 2 and not gts.is_monotonic_increasing:
            issues.append(f"non_monotonic:{sym}")
            invalid_syms += 1
        if len(gts) >= 2 and max_gap_days > 0:
            deltas = gts.diff().dt.total_seconds().dropna() / 86400.0
            if (deltas > max_gap_days).any():
                issues.append(f"abnormal_gap:{sym}")

    report.symbols_invalid = invalid_syms
    report.symbols_valid = max(0, report.symbols_received - invalid_syms)

    if expected_symbols:
        exp = {str(s) for s in expected_symbols}
        got = set(syms.unique())
        miss = sorted(exp - got)
        report.symbols_expected = len(exp)
        report.symbols_missing = len(miss)
        if miss:
            issues.append(f"symbols_missing:{miss[:10]}")
        report.coverage_ratio = (len(exp) - len(miss)) / len(exp) if exp else 0.0
        if min_coverage > 0 and report.coverage_ratio < min_coverage:
            issues.append(f"coverage_below:{report.coverage_ratio:.3f}<{min_coverage}")
    else:
        report.symbols_expected = report.symbols_received
        report.coverage_ratio = 1.0 if report.symbols_received else 0.0

    seen = set()
    uniq = []
    for i in issues:
        if i not in seen:
            seen.add(i)
            uniq.append(i)
    report.issues = uniq
    report.ok = len(uniq) == 0
    report.status = "PASS" if report.ok else "FAIL"
    return report


def ohlc_geometry_mask(df: pd.DataFrame) -> "pd.Series":
    """True = valid OHLC geometry for the row. Safe on missing columns (all False)."""
    if df is None or getattr(df, "empty", True):
        return pd.Series(dtype=bool)
    need = {"open", "high", "low", "close"}
    if not need.issubset(set(df.columns)):
        return pd.Series([False] * len(df), index=df.index)
    o = pd.to_numeric(df["open"], errors="coerce")
    h = pd.to_numeric(df["high"], errors="coerce")
    l = pd.to_numeric(df["low"], errors="coerce")
    c = pd.to_numeric(df["close"], errors="coerce")
    valid = (
        o.notna() & h.notna() & l.notna() & c.notna()
        & (h >= o) & (h >= c) & (h >= l)
        & (l <= o) & (l <= c) & (l <= h)
        & (c > 0)
    )
    return valid.fillna(False)


def quarantine_invalid_ohlc_geometry(
    df: pd.DataFrame,
    *,
    min_keep_ratio: float = 0.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Drop rows with invalid OHLC geometry BEFORE production DQ.

    Does NOT relax validate_ohlcv — production gate stays fail-closed.
    Returns (clean_df, audit_report).
    """
    if df is None or getattr(df, "empty", True):
        return df if df is not None else pd.DataFrame(), {
            "ok": False,
            "reason": "empty_frame",
            "rows_in": 0,
            "rows_out": 0,
            "rows_quarantined": 0,
            "symbols_quarantined": [],
            "symbols_fully_dropped": [],
        }
    work = df.copy()
    mask = ohlc_geometry_mask(work)
    bad = work.loc[~mask]
    good = work.loc[mask].copy()
    bad_syms: dict[str, int] = {}
    if not bad.empty and "symbol" in bad.columns:
        bad_syms = bad.groupby(bad["symbol"].astype(str)).size().astype(int).to_dict()
    fully_dropped = []
    if "symbol" in work.columns:
        for sym, n_bad in bad_syms.items():
            n_all = int((work["symbol"].astype(str) == sym).sum())
            if n_bad >= n_all:
                fully_dropped.append(sym)
    rows_in = len(work)
    rows_out = len(good)
    ratio = (rows_out / rows_in) if rows_in else 0.0
    report = {
        "ok": rows_out > 0 and ratio >= float(min_keep_ratio),
        "reason": "geometry_quarantine",
        "rows_in": rows_in,
        "rows_out": rows_out,
        "rows_quarantined": int((~mask).sum()),
        "keep_ratio": round(ratio, 6),
        "symbols_quarantined": sorted(bad_syms.keys()),
        "quarantine_counts": {k: int(v) for k, v in sorted(bad_syms.items(), key=lambda x: -x[1])[:50]},
        "symbols_fully_dropped": sorted(fully_dropped)[:100],
        "sample_bad_rows": (
            bad.head(10)[["timestamp", "symbol", "open", "high", "low", "close"]].astype(str).to_dict("records")
            if not bad.empty and set(REQUIRED_COLS).issubset(bad.columns)
            else []
        ),
    }
    return good.reset_index(drop=True), report
