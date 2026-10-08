"""OHLC geometry quarantine — invalid candles never reach production DQ as silent pass."""
from __future__ import annotations

import pandas as pd

from src.python.data.quality import (
    ohlc_geometry_mask,
    quarantine_invalid_ohlc_geometry,
    validate_ohlcv,
)


def _row(sym, ts, o, h, l, c, v=1.0):
    return {
        "timestamp": ts,
        "symbol": sym,
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": v,
    }


def test_quarantine_drops_low_gt_components():
    df = pd.DataFrame([
        _row("GOOD", "2026-10-01", 100, 110, 90, 105),
        _row("BAD", "2026-10-01", 100, 110, 120, 105),
        _row("GOOD", "2026-10-02", 105, 112, 100, 108),
    ])
    clean, rep = quarantine_invalid_ohlc_geometry(df)
    assert rep["rows_quarantined"] == 1
    assert "BAD" in rep["symbols_quarantined"]
    assert len(clean) == 2
    q = validate_ohlcv(clean)
    assert q.ok, q.issues


def test_validate_still_fails_on_raw_bad_frame():
    df = pd.DataFrame([
        _row("BAD", "2026-10-01", 100, 110, 120, 105),
    ])
    q = validate_ohlcv(df)
    assert not q.ok
    assert "low_gt_components" in q.issues


def test_quarantine_empty_if_all_bad():
    df = pd.DataFrame([
        _row("X", "2026-10-01", 10, 11, 15, 10),
        _row("Y", "2026-10-01", 20, 21, 25, 20),
    ])
    clean, rep = quarantine_invalid_ohlc_geometry(df)
    assert len(clean) == 0
    assert rep["rows_quarantined"] == 2


def test_mask_requires_high_ge_components():
    df = pd.DataFrame([_row("Z", "2026-10-01", 100, 90, 80, 95)])
    m = ohlc_geometry_mask(df)
    assert bool(m.iloc[0]) is False
