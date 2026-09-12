from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd

@dataclass
class QualityReport:
    ok: bool = True
    issues: list[str] = field(default_factory=list)

def validate_ohlcv(df: pd.DataFrame, max_gap_days: float = 45.0) -> QualityReport:
    issues: list[str] = []
    if df is None or df.empty:
        return QualityReport(False, ["empty_frame"])
    required = {"timestamp", "symbol", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        issues.append(f"missing_cols:{sorted(missing)}")
    if "close" in df.columns and (df["close"].isna().any() or (df["close"] <= 0).any()):
        issues.append("invalid_close")
    if "high" in df.columns and "low" in df.columns and (df["high"] < df["low"]).any():
        issues.append("high_lt_low")
    if "timestamp" in df.columns:
        ts = pd.to_datetime(df["timestamp"], errors="coerce")
        if ts.isna().any():
            issues.append("bad_timestamps")
    return QualityReport(ok=len(issues) == 0, issues=issues)
