"""Data quality is mandatory before signals enter the ops path."""
from __future__ import annotations

import pandas as pd

from src.python.crypto.data_quality import validate_ohlcv_frame


def test_impossible_ohlc_blocks():
    df = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-01T00:00:00+00:00",
                "open": 10.0,
                "high": 9.0,
                "low": 11.0,
                "close": 10.0,
                "volume": 1.0,
            }
        ]
    )
    v = validate_ohlcv_frame(df, symbol="X/USDT")
    assert v["ok"] is False
    assert any("IMPOSSIBLE" in i for i in v["issues"])


def test_signal_bot_calls_validate():
    import inspect
    import src.python.crypto.signal_bot as sb

    src = inspect.getsource(sb.run_crypto_paper)
    assert "validate_ohlcv_frame" in src
    assert "DATA_QUALITY_BLOCK" in src
    assert "data_quality_blocks" in src
