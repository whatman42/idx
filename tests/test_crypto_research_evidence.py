"""Historical evidence runner — ends at manual review, never auto paper."""
from __future__ import annotations

import pandas as pd

from src.python.crypto.research_evidence import run_historical_evidence


def _bars() -> pd.DataFrame:
    rows = []
    px = 100.0
    for i in range(45):
        px *= 1.012
        rows.append(
            {
                "timestamp": f"2026-09-01T{i:02d}:00:00+00:00",
                "symbol": "ETH/USDT",
                "open": px * 0.999,
                "high": px * 1.01,
                "low": px * 0.99,
                "close": px,
                "volume": 50.0 + i,
            }
        )
    return pd.DataFrame(rows)


def test_evidence_injected_bars_manual_review():
    rep = run_historical_evidence(
        bars=_bars(),
        min_trades=3,
        persist_gate=False,
        out_dir="/tmp/crypto_evidence_test",
    )
    assert rep["status"] == "READY_FOR_MANUAL_REVIEW"
    assert rep["live_execution"] is False
    assert rep["auto_paper_allowed"] is False
    assert rep["manual_review_required"] is True
    assert rep["paper_ledger_mutated"] is False
    assert "PAPER_ALLOWED" not in (rep.get("next_allowed_actions") or [])
    assert rep["shadow"]["paper_eligible"] is False


def test_empty_bars_no_crash():
    rep = run_historical_evidence(
        bars=pd.DataFrame(),
        persist_gate=False,
        out_dir="/tmp/crypto_evidence_empty",
    )
    assert rep["status"] == "NO_BARS"
    assert rep["auto_paper_allowed"] is False
