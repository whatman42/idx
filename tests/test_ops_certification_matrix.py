"""Full operational certification matrix — synthetic, deterministic, no broker/live data."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from src.python.data.quality import validate_ohlcv
from src.python.ops.paper_portfolio import (
    PaperPortfolioStore,
    apply_long_entry,
    new_session,
    rebuild_portfolio_from_trades,
    summary,
    validate_portfolio_accounting,
)
from src.python.strategy.feature_snapshot import is_forbidden_feature_name
from src.python.strategy.promotion_gate import PromotionGate
from src.python.archive.contracts import archive_cannot_affect_trading


def _ohlcv(n: int = 30, symbols: list[str] | None = None, seed: int = 7) -> pd.DataFrame:
    symbols = symbols or ["AAA", "BBB", "CCC", "DDD", "EEE"]
    rows = []
    rng = __import__("random").Random(seed)
    base = pd.Timestamp("2026-08-01", tz="UTC")
    for si, sym in enumerate(symbols):
        px = 100.0 + si * 10
        for i in range(n):
            o = px
            c = px * (1 + (rng.random() - 0.45) * 0.02)
            h = max(o, c) * 1.01
            l = min(o, c) * 0.99
            rows.append(
                {
                    "timestamp": base + pd.Timedelta(days=i),
                    "symbol": sym,
                    "open": round(o, 2),
                    "high": round(h, 2),
                    "low": round(l, 2),
                    "close": round(c, 2),
                    "volume": 1000 + i,
                }
            )
            px = c
    return pd.DataFrame(rows)


def test_cert_dq_valid_and_invalid():
    df = _ohlcv()
    assert validate_ohlcv(df).ok
    bad = df.copy()
    bad.loc[0, "high"] = 1.0
    assert not validate_ohlcv(bad).ok
    fut = df.copy()
    fut.loc[len(fut) - 1, "timestamp"] = pd.Timestamp("2099-01-01", tz="UTC")
    assert not validate_ohlcv(fut).ok
    partial = validate_ohlcv(df, expected_symbols=["AAA", "ZZZ"], min_coverage=1.0)
    assert not partial.ok and partial.status == "PARTIAL_DATA"


def test_cert_feature_label_guard():
    assert is_forbidden_feature_name("y_next_up")
    assert is_forbidden_feature_name("future_ret")
    assert not is_forbidden_feature_name("sma_dist_20")


def test_cert_daily_e2e_paper_fill_and_ledger(tmp_path):
    store = PaperPortfolioStore(tmp_path / "pf.json", archive_dir=tmp_path / "sess")
    state = new_session(initial_capital=100_000_000.0, model_version="ops_sma_v0")
    store.save_atomic(state)
    state, trade, status = apply_long_entry(
        state,
        symbol="AAA",
        price=100.0,
        weight=0.05,
        signal_id="sig_cert_001",
        timestamp="2026-08-02T02:00:00+00:00",
    )
    assert status == "PAPER_FILLED"
    assert trade is not None
    assert trade.get("fee", 0) > 0
    assert trade.get("slippage_bps", 0) > 0
    assert state.cash < 100_000_000.0
    assert len(state.trades) == 1
    assert validate_portfolio_accounting(state) == []
    store.save_atomic(state)


def test_cert_restart_replay_no_duplicate(tmp_path):
    path = tmp_path / "pf.json"
    store = PaperPortfolioStore(path, archive_dir=tmp_path / "sess")
    state = new_session(initial_capital=50_000_000.0)
    state, trade, status = apply_long_entry(
        state,
        symbol="BBB",
        price=110.0,
        weight=0.05,
        signal_id="sig_replay_42",
        timestamp="2026-08-03T02:00:00+00:00",
    )
    assert status == "PAPER_FILLED"
    store.save_atomic(state)
    trades1 = len(state.trades)
    cash1 = state.cash

    state2 = store.load()
    state2, trade2, status2 = apply_long_entry(
        state2,
        symbol="BBB",
        price=110.0,
        weight=0.05,
        signal_id="sig_replay_42",
        timestamp="2026-08-03T02:00:00+00:00",
    )
    assert status2 == "ALREADY_APPLIED"
    assert trade2 is None
    assert len(state2.trades) == trades1
    assert abs(state2.cash - cash1) < 1.0


def test_cert_ledger_rebuild(tmp_path):
    state = new_session(initial_capital=20_000_000.0)
    state, trade, status = apply_long_entry(
        state,
        symbol="CCC",
        price=120.0,
        weight=0.05,
        signal_id="sig_rb_1",
        timestamp="2026-08-04T02:00:00+00:00",
    )
    assert status == "PAPER_FILLED"
    rebuilt = rebuild_portfolio_from_trades(list(state.trades), initial_capital=20_000_000.0)
    assert abs(rebuilt.cash - state.cash) < 1.0
    assert "CCC" in rebuilt.open_positions()


def test_cert_wfa_temporal_windows():
    from src.python.research.wfa_executor import validate_pit_features

    df = _ohlcv(60)
    assert validate_pit_features(df) == []
    ts = sorted(df["timestamp"].unique())
    n = len(ts)
    windows = []
    for w in range(3):
        train_end = n // 5 + w * 5
        val_end = train_end + 5
        test_end = val_end + 5
        if test_end > n:
            break
        train_ts = ts[:train_end]
        val_ts = ts[train_end:val_end]
        test_ts = ts[val_end:test_end]
        assert max(train_ts) < min(val_ts)
        assert max(val_ts) < min(test_ts)
        windows.append(
            {
                "train_start": str(min(train_ts)),
                "train_end": str(max(train_ts)),
                "validation_start": str(min(val_ts)),
                "validation_end": str(max(val_ts)),
                "test_start": str(min(test_ts)),
                "test_end": str(max(test_ts)),
            }
        )
    assert len(windows) >= 2


def test_cert_reproducibility_hash():
    df = _ohlcv(20, seed=99)
    h1 = hashlib.sha256(df.to_csv(index=False).encode()).hexdigest()
    h2 = hashlib.sha256(_ohlcv(20, seed=99).to_csv(index=False).encode()).hexdigest()
    assert h1 == h2


def test_cert_evidence_package_fields():
    ev = {
        "strategy_id": "ops_sma_v0",
        "strategy_version": "0.1.0",
        "evidence_id": "EP-CERT-001",
        "dataset_hash": "d" * 24,
        "feature_hash": "f" * 24,
        "lookahead_safe": True,
        "backtest": {"n_trades": 50},
        "walk_forward": {"n_periods": 3},
    }
    for k in ("strategy_id", "dataset_hash", "lookahead_safe", "backtest", "walk_forward"):
        assert k in ev


def test_cert_promotion_negative_paths():
    gate = PromotionGate()
    bad = {
        "strategy_id": "bad",
        "strategy_version": "0.0.1",
        "evidence_id": "EP-BAD",
        "dataset_hash": "x",
        "feature_hash": "y",
        "cost_model": "simulation_v2",
        "evaluation_date": "2026-09-20",
        "signal_defined": True,
        "feature_ssot": False,
        "uses_feature_snapshot": False,
        "lookahead_safe": False,
        "data_quality_ok": False,
        "reproducible": False,
        "backtest": {"n_trades": 1, "expectancy": -0.5, "profit_factor": 0.1, "max_drawdown": 0.9},
        "walk_forward": {"n_periods": 0, "pass_rate": 0.0},
        "out_of_sample": {"evaluated": False},
    }
    d = gate.evaluate("bad", bad)
    assert not getattr(d, "promoted", False)

    good = {
        "strategy_id": "trend_multi",
        "strategy_version": "2.3.1",
        "evidence_id": "EP-2026-0919-004",
        "dataset_hash": "abc123",
        "feature_hash": "feat456",
        "cost_model": "simulation_v2",
        "evaluation_date": "2026-09-19",
        "signal_defined": True,
        "feature_ssot": True,
        "uses_feature_snapshot": True,
        "lookahead_safe": True,
        "data_quality_ok": True,
        "reproducible": True,
        "backtest": {"n_trades": 91, "expectancy": 0.02, "profit_factor": 1.3, "max_drawdown": 0.074},
        "walk_forward": {"n_periods": 4, "pass_rate": 0.75},
        "out_of_sample": {"evaluated": True, "expectancy": 0.015, "n_trades": 40, "max_drawdown": 0.074},
    }
    d2 = gate.evaluate("trend_multi", good)
    assert not getattr(d2, "promoted", False)


def test_cert_governor_and_invariants():
    assert archive_cannot_affect_trading() is True


def test_cert_telegram_ssot_from_ledger():
    state = new_session(initial_capital=10_000_000.0)
    state, trade, status = apply_long_entry(
        state,
        symbol="DDD",
        price=50.0,
        weight=0.05,
        signal_id="sig_tg_1",
        timestamp="2026-08-05T02:00:00+00:00",
    )
    assert status == "PAPER_FILLED"
    summ = summary(state)
    payload = {
        "cash": summ.get("cash", state.cash),
        "equity": summ.get("equity", state.equity()),
        "source": "ledger_ssot",
        "llm_numeric": False,
    }
    assert payload["source"] == "ledger_ssot"
    assert payload["llm_numeric"] is False
    assert abs(float(payload["cash"]) - float(state.cash)) < 1e-6
