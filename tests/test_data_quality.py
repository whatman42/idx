"""Data quality contract — fail-closed OHLCV validation."""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from src.python.data.quality import universe_coverage_report, validate_ohlcv


def _base(**over):
    rows = {
        "timestamp": pd.to_datetime(
            ["2026-09-15 09:00:00+00:00", "2026-09-16 09:00:00+00:00", "2026-09-17 09:00:00+00:00"]
        ),
        "symbol": ["AAA", "AAA", "AAA"],
        "open": [100.0, 101.0, 102.0],
        "high": [105.0, 106.0, 107.0],
        "low": [99.0, 100.0, 101.0],
        "close": [104.0, 105.0, 106.0],
        "volume": [1000, 1100, 1200],
    }
    rows.update(over)
    return pd.DataFrame(rows)


def test_valid_passes():
    r = validate_ohlcv(_base())
    assert r.ok and r.status == "PASS"


def test_empty_fail():
    r = validate_ohlcv(pd.DataFrame())
    assert not r.ok and r.status == "DATA_UNAVAILABLE"


def test_high_lt_low():
    df = _base()
    df.loc[1, "high"] = 50.0
    r = validate_ohlcv(df)
    assert not r.ok
    assert any("high_lt" in i for i in r.issues)


def test_duplicate_candle():
    df = _base()
    df.loc[2, "timestamp"] = df.loc[1, "timestamp"]
    r = validate_ohlcv(df)
    assert not r.ok
    assert any("duplicate" in i for i in r.issues)


def test_future_timestamp():
    df = _base()
    df.loc[2, "timestamp"] = pd.Timestamp("2099-01-01", tz="UTC")
    r = validate_ohlcv(df, now=datetime(2026, 9, 18, tzinfo=timezone.utc))
    assert not r.ok
    assert any("future" in i for i in r.issues)


def test_negative_volume():
    df = _base()
    df.loc[0, "volume"] = -1
    r = validate_ohlcv(df)
    assert not r.ok
    assert any("negative:volume" in i for i in r.issues)


def test_partial_universe():
    df = _base()
    r = validate_ohlcv(df, expected_symbols=["AAA", "BBB"], min_coverage=1.0)
    assert not r.ok
    assert r.status == "PARTIAL_DATA"
    assert r.symbols_missing == 1


def test_coverage_report():
    cov = universe_coverage_report(["A", "B", "C"], ["A", "B"], valid=["A"])
    assert cov["symbols_missing"] == 1
    assert cov["status"] == "PARTIAL_DATA"


def test_no_mutation():
    df = _base()
    orig = df.copy()
    validate_ohlcv(df)
    pd.testing.assert_frame_equal(df, orig)
