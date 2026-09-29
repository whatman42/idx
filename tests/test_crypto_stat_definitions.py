"""VALID fold/symbol definitions — zero-trade is insufficient evidence."""
from __future__ import annotations

from src.python.crypto.research_evidence import _symbol_consistency


def test_symbol_no_trades_excluded_from_ratio():
    rows = [
        {"symbol": "A", "evidence_class": "VALID", "n_trades": 3, "expectancy": 1.0},
        {"symbol": "B", "evidence_class": "VALID", "n_trades": 2, "expectancy": -0.5},
        {"symbol": "C", "evidence_class": "NO_TRADES", "n_trades": 0, "expectancy": None},
    ]
    c = _symbol_consistency(rows)
    assert c["n_valid"] == 2
    assert c["n_no_trades"] == 1
    assert c["positive_expectancy_symbols"] == 1
    assert c["positive_symbol_ratio"] == 0.5


def test_all_no_trades_ratio_none():
    rows = [
        {"symbol": "A", "evidence_class": "NO_TRADES", "n_trades": 0, "expectancy": None},
    ]
    c = _symbol_consistency(rows)
    assert c["n_valid"] == 0
    assert c["positive_symbol_ratio"] is None
    assert c["warning"] == "NO_VALID_SYMBOLS"


def test_fold_ratio_excludes_zero_trade_logic():
    windows = [
        {"n_trades": 2, "expectancy": 1.0},
        {"n_trades": 0, "expectancy": 0.0},
        {"n_trades": 3, "expectancy": -0.2},
    ]
    valid = [w for w in windows if w["n_trades"] > 0]
    pos = sum(1 for w in valid if w["expectancy"] > 0)
    assert pos / len(valid) == 0.5
    assert len(valid) == 2
