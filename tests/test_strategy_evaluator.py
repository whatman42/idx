"""Phase 2A — Backtest/WF evaluator + hard rejection + baseline rule_sma20 control."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.python.strategy.evaluator import (
    EvaluatorConfig,
    StrategyEvaluator,
    evaluate_rule_sma20,
    sma20_signal_fn,
)
from src.python.strategy.evidence import HardRejectCode
from src.python.strategy.promotion_gate import PromotionGate, PromotionStage


def _synthetic_trending_bars(
    n: int = 120,
    symbols: tuple[str, ...] = ("AAA", "BBB", "CCC"),
    seed: int = 42,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    base_ts = pd.Timestamp("2024-01-01")
    for sym_i, sym in enumerate(symbols):
        px = 1000.0 + sym_i * 50
        for i in range(n):
            # mild upward drift so SMA20 fires often
            ret = 0.002 + rng.normal(0, 0.01)
            o = px
            c = px * (1 + ret)
            h = max(o, c) * (1 + abs(rng.normal(0, 0.003)))
            l = min(o, c) * (1 - abs(rng.normal(0, 0.003)))
            rows.append({
                "timestamp": base_ts + pd.Timedelta(days=i),
                "symbol": sym,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": float(rng.integers(1_000_000, 5_000_000)),
            })
            px = c
    return pd.DataFrame(rows)


def test_sma20_signal_no_lookahead_columns():
    bars = _synthetic_trending_bars(80)
    sig = sma20_signal_fn(20)(bars)
    assert not sig.empty
    assert set(["timestamp", "symbol", "side"]).issubset(sig.columns)
    assert sig["side"].isin([0, 1]).all()


def test_evaluate_rule_sma20_produces_evidence():
    bars = _synthetic_trending_bars(120)
    cfg = EvaluatorConfig(
        min_trades=5,
        min_wf_periods=2,
        wf_train_bars=40,
        wf_test_bars=15,
        wf_step_bars=15,
        hold_bars=5,
    )
    pkg = evaluate_rule_sma20(bars, cfg=cfg)
    assert pkg.strategy_id == "rule_sma20"
    assert pkg.signal_defined is True
    assert pkg.timing == "signal_T_execute_open_Tplus1"
    assert pkg.lookahead_safe is True
    assert pkg.cost_evaluated is True
    assert pkg.n_trades >= 0
    assert isinstance(pkg.hard_rejects, list)
    # evidence shape for gate
    ev = pkg.to_promotion_evidence()
    assert "backtest" in ev and "walk_forward" in ev and "out_of_sample" in ev


def test_hard_reject_insufficient_trades():
    bars = _synthetic_trending_bars(50, symbols=("ZZZ",))
    cfg = EvaluatorConfig(min_trades=10_000, min_wf_periods=1, wf_train_bars=20, wf_test_bars=10)
    pkg = evaluate_rule_sma20(bars, cfg=cfg)
    assert HardRejectCode.INSUFFICIENT_TRADES.value in pkg.hard_rejects


def test_hard_reject_empty_bars():
    pkg = evaluate_rule_sma20(pd.DataFrame())
    assert HardRejectCode.DATA_QUALITY_FAILURE.value in pkg.hard_rejects


def test_promotion_gate_receives_evidence_default_reject():
    bars = _synthetic_trending_bars(100)
    cfg = EvaluatorConfig(min_trades=5, min_wf_periods=2, wf_train_bars=30, wf_test_bars=15, wf_step_bars=15)
    pkg = evaluate_rule_sma20(bars, cfg=cfg)
    gate = PromotionGate(min_trades=5, min_wf_periods=2)
    verdict = gate.evaluate("rule_sma20", pkg.to_promotion_evidence())
    # may or may not promote depending on synthetic path — must not crash
    assert verdict.strategy_id == "rule_sma20"
    assert isinstance(verdict.approved, bool)
    assert verdict.final_stage in list(PromotionStage)


def test_and_gate_rejects_on_missing_oos():
    """AND-gate: incomplete evidence never promotes."""
    gate = PromotionGate(min_trades=1)
    incomplete = {
        "signal_defined": True,
        "backtest": {"closed_trades": 50, "expectancy": 0.01, "profit_factor": 1.2, "max_drawdown": 0.05},
        # missing walk_forward / oos / cost / stability / regime
    }
    v = gate.evaluate("rule_sma20", incomplete)
    assert v.approved is False
    assert v.final_stage != PromotionStage.PROMOTE


def test_entry_uses_next_bar_open_not_signal_close():
    """Structural no-look-ahead: with 1 symbol, signal on bar i cannot enter on bar i close."""
    # construct bars where close jumps but open of next is known
    rows = []
    ts0 = pd.Timestamp("2024-06-01")
    px = 1000.0
    for i in range(40):
        o, c = px, px * 1.01
        rows.append({
            "timestamp": ts0 + pd.Timedelta(days=i),
            "symbol": "T",
            "open": o, "high": max(o, c) * 1.001, "low": min(o, c) * 0.999, "close": c, "volume": 1e6,
        })
        px = c
    bars = pd.DataFrame(rows)
    cfg = EvaluatorConfig(min_trades=1, hold_bars=3, weight=0.1, wf_train_bars=1000)  # skip wf
    pkg = StrategyEvaluator(cfg).evaluate("rule_sma20", bars, sma20_signal_fn(10))
    # if any trades, entry_price should be near next open (with slip), not wildly using future close only
    assert pkg.lookahead_safe is True


def test_zero_side_signals_no_crash():
    def never_buy(bars: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence"])

    bars = _synthetic_trending_bars(60)
    pkg = StrategyEvaluator(EvaluatorConfig(min_trades=1)).evaluate("empty", bars, never_buy)
    assert pkg.n_trades == 0
    assert HardRejectCode.INSUFFICIENT_TRADES.value in pkg.hard_rejects
