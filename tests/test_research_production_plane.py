"""Lock RESEARCH vs PRODUCTION plane contract.

Evaluator generates evidence only; never production authority or state writes.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd

from src.python.strategy import evaluator as evaluator_mod
from src.python.strategy.evaluator import StrategyEvaluator, EvaluatorConfig
from src.python.strategy.evidence import EvidencePackage
from src.python.strategy.plane_contract import (
    PRODUCTION_FORBIDDEN_IMPORTS,
    TIMING_CONTRACT,
    describe_plane_contract,
)
from src.python.strategy.promotion_gate import PromotionGate


def test_describe_plane_contract_roles():
    d = describe_plane_contract()
    assert d["live_execution"] is False
    assert d["research"]["writes_ledger"] is False
    assert d["research"]["writes_paper"] is False
    assert d["research"]["sends_telegram"] is False
    assert d["research"]["mutates_champion"] is False
    assert d["research"]["authority"] is False
    assert d["research"]["output"] == "EvidencePackage"
    assert "Evaluator→Ledger" in d["forbidden_edges"]
    assert d["research"]["timing"] == TIMING_CONTRACT


def test_evaluator_module_flags():
    assert getattr(evaluator_mod, "PLANE", None) == "RESEARCH"
    assert getattr(evaluator_mod, "EXECUTION_AUTHORITY", True) is False
    assert getattr(evaluator_mod, "LIVE_EXECUTION", True) is False


def test_evaluator_source_has_no_production_calls():
    src = Path(evaluator_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: set[str] = set()
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            for alias in node.names:
                imported.add(f"{node.module}.{alias.name}")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
    for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
        assert not any(forbidden in m or m.startswith(forbidden) for m in imported), forbidden
    for sym in ("apply_long_entry", "send_telegram", "promote_champion", "PaperPortfolioStore"):
        assert sym not in called


def test_evaluate_returns_evidence_package_only():
    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=80, freq="B"),
            "symbol": ["TEST"] * 80,
            "open": [100.0] * 80,
            "high": [101.0] * 80,
            "low": [99.0] * 80,
            "close": [100.0 + (i % 5) * 0.1 for i in range(80)],
            "volume": [1e6] * 80,
        }
    )

    def signal_fn(df: pd.DataFrame) -> pd.DataFrame:
        rows = []
        for i, row in df.iterrows():
            if i % 10 == 9:
                rows.append(
                    {
                        "timestamp": row["timestamp"],
                        "symbol": row["symbol"],
                        "side": 1,
                        "confidence": 0.5,
                        "close": row["close"],
                    }
                )
        return pd.DataFrame(rows)

    pkg = StrategyEvaluator(
        EvaluatorConfig(min_trades=1, wf_train_bars=20, wf_test_bars=10, wf_step_bars=10)
    ).evaluate("test_strategy", bars, signal_fn)
    assert isinstance(pkg, EvidencePackage)
    assert pkg.strategy_id == "test_strategy"
    assert not hasattr(pkg, "side")
    assert not hasattr(pkg, "order_intent")


def test_promotion_gate_is_separate_from_evaluator():
    src = Path(evaluator_mod.__file__).read_text(encoding="utf-8")
    assert "PromotionGate(" not in src
    assert "approved = True" not in src
    gate = PromotionGate()
    assert gate is not None


def test_timing_contract_documented():
    cfg = EvaluatorConfig()
    assert "Tplus1" in cfg.timing or "T+1" in cfg.timing.replace(" ", "")
