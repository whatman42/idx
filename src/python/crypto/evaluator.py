"""Crypto Strategy Evaluator — RESEARCH PLANE ONLY.

Default signal path uses Crypto Feature Engine + FeatureSnapshot.
Never writes CryptoPaperLedger ops. Never enables LIVE_EXECUTION.
Base: USDT continuous quantity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from src.python.crypto.config import (
    CRYPTO_FEE_BUY_BPS,
    CRYPTO_FEE_SELL_BPS,
    CRYPTO_SLIPPAGE_BPS,
    CRYPTO_SL_PCT,
    CRYPTO_TP_PCT,
    assert_crypto_paper_only,
)

PLANE = "CRYPTO_RESEARCH"
LIVE_EXECUTION = False


@dataclass
class CryptoEvaluatorConfig:
    initial_capital_usdt: float = 10_000.0
    fee_buy_bps: float = CRYPTO_FEE_BUY_BPS
    fee_sell_bps: float = CRYPTO_FEE_SELL_BPS
    slippage_bps: float = CRYPTO_SLIPPAGE_BPS
    hold_bars: int = 5
    sl_pct: float = CRYPTO_SL_PCT
    tp_pct: float = CRYPTO_TP_PCT
    weight: float = 0.10
    min_trades: int = 20
    max_drawdown: float = 0.40
    min_expectancy: float = 0.0
    wf_train_bars: int = 40
    wf_test_bars: int = 15
    wf_step_bars: int = 15
    timing: str = "signal_T_execute_next_open"


def _buy_px(px: float, slip_bps: float) -> float:
    return float(px) * (1.0 + slip_bps / 10_000.0)


def _sell_px(px: float, slip_bps: float) -> float:
    return float(px) * (1.0 - slip_bps / 10_000.0)


def _fee(notional: float, bps: float) -> float:
    return abs(float(notional)) * bps / 10_000.0


def _feature_signal_fn(bars: pd.DataFrame) -> pd.DataFrame:
    from src.python.crypto.features import build_crypto_features
    from src.python.crypto.scorer import CryptoSma20Scorer

    res = build_crypto_features(bars)
    if res.df.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "close"])
    scored = CryptoSma20Scorer().score_frame(res.df)
    if scored.empty:
        return scored
    if "price" in scored.columns and "close" not in scored.columns:
        scored = scored.rename(columns={"price": "close"})
    return scored


def _sma_signal(bars: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
    rows: list[dict] = []
    if bars is None or bars.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "close"])
    df = bars.sort_values(["symbol", "timestamp"]).copy()
    for sym, g in df.groupby("symbol", sort=False):
        g = g.reset_index(drop=True)
        if len(g) < lookback + 1:
            continue
        close = g["close"].astype(float)
        sma = close.rolling(lookback, min_periods=lookback).mean()
        for i in range(lookback, len(g)):
            if pd.isna(sma.iloc[i]):
                continue
            if float(close.iloc[i]) > float(sma.iloc[i]):
                rows.append(
                    {
                        "timestamp": g.iloc[i]["timestamp"],
                        "symbol": str(sym),
                        "side": 1,
                        "confidence": 0.6,
                        "close": float(close.iloc[i]),
                    }
                )
    return pd.DataFrame(rows)


def backtest_crypto(
    bars: pd.DataFrame,
    *,
    cfg: Optional[CryptoEvaluatorConfig] = None,
    signal_fn: Optional[Callable[[pd.DataFrame], pd.DataFrame]] = None,
) -> dict[str, Any]:
    assert_crypto_paper_only()
    cfg = cfg or CryptoEvaluatorConfig()
    signal_fn = signal_fn or _feature_signal_fn
    if bars is None or bars.empty:
        return _empty_result(cfg, reason="NO_BARS")

    df = bars.sort_values(["symbol", "timestamp"]).reset_index(drop=True).copy()
    if "open" not in df.columns:
        df["open"] = df["close"]
    signals = signal_fn(df)
    if signals is None or signals.empty:
        return _empty_result(cfg, reason="NO_SIGNALS")

    cash = float(cfg.initial_capital_usdt)
    equity_curve: list[float] = [cash]
    trades: list[dict] = []
    open_pos: dict[str, dict] = {}
    by_sym = {str(s): g.reset_index(drop=True) for s, g in df.groupby("symbol", sort=False)}

    for _, srow in signals.sort_values("timestamp").iterrows():
        sym = str(srow["symbol"])
        g = by_sym.get(sym)
        if g is None or len(g) < 2 or sym in open_pos:
            continue
        ts = srow["timestamp"]
        idxs = g.index[g["timestamp"] == ts].tolist()
        if not idxs:
            continue
        i = int(idxs[0])
        if i + 1 >= len(g):
            continue
        entry_row = g.iloc[i + 1]
        entry_px = _buy_px(float(entry_row["open"]), cfg.slippage_bps)
        notional = cash * cfg.weight
        if notional <= 0 or entry_px <= 0:
            continue
        qty = notional / entry_px
        entry_fee = _fee(notional, cfg.fee_buy_bps)
        if notional + entry_fee > cash:
            continue
        cash -= notional + entry_fee
        open_pos[sym] = {
            "entry_px": entry_px,
            "qty": qty,
            "entry_fee": entry_fee,
            "tp": entry_px * (1.0 + cfg.tp_pct),
            "sl": entry_px * (1.0 - cfg.sl_pct),
        }
        exit_i = min(i + 1 + cfg.hold_bars, len(g) - 1)
        exit_px = None
        exit_reason = "TIME"
        for j in range(i + 2, exit_i + 1):
            hi = float(g.iloc[j]["high"]) if "high" in g.columns else float(g.iloc[j]["close"])
            lo = float(g.iloc[j]["low"]) if "low" in g.columns else float(g.iloc[j]["close"])
            if lo <= open_pos[sym]["sl"]:
                exit_px = _sell_px(open_pos[sym]["sl"], cfg.slippage_bps)
                exit_reason = "SL"
                break
            if hi >= open_pos[sym]["tp"]:
                exit_px = _sell_px(open_pos[sym]["tp"], cfg.slippage_bps)
                exit_reason = "TP"
                break
        if exit_px is None:
            exit_px = _sell_px(float(g.iloc[exit_i]["close"]), cfg.slippage_bps)
        pos = open_pos.pop(sym)
        sell_notional = pos["qty"] * exit_px
        sell_fee = _fee(sell_notional, cfg.fee_sell_bps)
        cash += sell_notional - sell_fee
        pnl = (exit_px - pos["entry_px"]) * pos["qty"] - pos["entry_fee"] - sell_fee
        trades.append({"symbol": sym, "entry": pos["entry_px"], "exit": exit_px, "qty": pos["qty"], "pnl": pnl, "reason": exit_reason})
        equity_curve.append(cash)

    for sym, pos in list(open_pos.items()):
        g = by_sym[sym]
        exit_px = _sell_px(float(g.iloc[-1]["close"]), cfg.slippage_bps)
        sell_notional = pos["qty"] * exit_px
        sell_fee = _fee(sell_notional, cfg.fee_sell_bps)
        cash += sell_notional - sell_fee
        pnl = (exit_px - pos["entry_px"]) * pos["qty"] - pos["entry_fee"] - sell_fee
        trades.append({"symbol": sym, "entry": pos["entry_px"], "exit": exit_px, "qty": pos["qty"], "pnl": pnl, "reason": "EOD"})
        equity_curve.append(cash)

    pnls = [t["pnl"] for t in trades]
    n = len(trades)
    expectancy = float(np.mean(pnls)) if n else 0.0
    win_rate = float(np.mean([1.0 if p > 0 else 0.0 for p in pnls])) if n else 0.0
    eq = np.array(equity_curve, dtype=float)
    peak = np.maximum.accumulate(eq) if len(eq) else np.array([cfg.initial_capital_usdt])
    dd = float(np.max((peak - eq) / np.maximum(peak, 1e-12))) if len(eq) else 0.0
    return {
        "plane": PLANE,
        "live_execution": False,
        "base_currency": "USDT",
        "n_trades": n,
        "expectancy": expectancy,
        "win_rate": win_rate,
        "total_pnl": cash - cfg.initial_capital_usdt,
        "final_equity": cash,
        "max_drawdown": dd,
        "trades": trades[:200],
        "config": asdict(cfg),
        "hard_reject": _hard_reject(n, expectancy, dd, cfg),
        "signal_path": "feature_snapshot",
    }


def walk_forward_crypto(
    bars: pd.DataFrame,
    *,
    cfg: Optional[CryptoEvaluatorConfig] = None,
) -> dict[str, Any]:
    assert_crypto_paper_only()
    cfg = cfg or CryptoEvaluatorConfig()
    if bars is None or bars.empty:
        return {"windows": [], "n_windows": 0, "live_execution": False, "plane": PLANE}
    df = bars.sort_values("timestamp").reset_index(drop=True)
    ts = sorted(df["timestamp"].unique())
    windows: list[dict] = []
    i = 0
    while i + cfg.wf_train_bars + cfg.wf_test_bars <= len(ts):
        train_ts = set(ts[i : i + cfg.wf_train_bars])
        test_ts = set(ts[i + cfg.wf_train_bars : i + cfg.wf_train_bars + cfg.wf_test_bars])
        window_bars = df[df["timestamp"].isin(train_ts | test_ts)]
        res = backtest_crypto(window_bars, cfg=cfg)
        windows.append({
            "train_start": str(ts[i]),
            "test_start": str(ts[i + cfg.wf_train_bars]),
            "n_trades": res["n_trades"],
            "expectancy": res["expectancy"],
            "max_drawdown": res["max_drawdown"],
            "total_pnl": res["total_pnl"],
        })
        i += cfg.wf_step_bars
    n_tr = sum(w["n_trades"] for w in windows)
    exp = float(np.mean([w["expectancy"] for w in windows])) if windows else 0.0
    mdd = float(np.max([w["max_drawdown"] for w in windows])) if windows else 0.0
    return {
        "plane": PLANE,
        "live_execution": False,
        "base_currency": "USDT",
        "n_windows": len(windows),
        "n_trades": n_tr,
        "expectancy": exp,
        "max_drawdown": mdd,
        "windows": windows,
        "hard_reject": _hard_reject(n_tr, exp, mdd, cfg),
        "config": asdict(cfg),
        "signal_path": "feature_snapshot",
    }


def build_evidence_package(
    *,
    strategy_id: str,
    strategy_version: str,
    backtest: dict[str, Any],
    walk_forward: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    wf = walk_forward or {}
    return {
        "domain": "CRYPTO",
        "plane": PLANE,
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "n_trades": int(backtest.get("n_trades") or 0),
        "expectancy": float(backtest.get("expectancy") or 0.0),
        "max_drawdown": float(backtest.get("max_drawdown") or 0.0),
        "win_rate": backtest.get("win_rate"),
        "total_pnl": backtest.get("total_pnl"),
        "walk_forward": {
            "n_windows": wf.get("n_windows", 0),
            "n_trades": wf.get("n_trades", 0),
            "expectancy": wf.get("expectancy"),
            "max_drawdown": wf.get("max_drawdown"),
        },
        "hard_reject": backtest.get("hard_reject") or [],
        "fee_model": "CRYPTO_SIMULATION",
        "base_currency": "USDT",
        "live_execution": False,
        "origin": "CRYPTO_EVALUATOR",
        "signal_path": backtest.get("signal_path", "feature_snapshot"),
    }


def _hard_reject(n: int, exp: float, mdd: float, cfg: CryptoEvaluatorConfig) -> list[str]:
    codes: list[str] = []
    if n < cfg.min_trades:
        codes.append(f"INSUFFICIENT_TRADES:{n}<{cfg.min_trades}")
    if exp < cfg.min_expectancy and n > 0:
        codes.append("NEGATIVE_EXPECTANCY")
    if mdd > cfg.max_drawdown:
        codes.append(f"MAX_DRAWDOWN:{mdd:.3f}>{cfg.max_drawdown}")
    return codes


def _empty_result(cfg: CryptoEvaluatorConfig, reason: str) -> dict[str, Any]:
    return {
        "plane": PLANE,
        "live_execution": False,
        "base_currency": "USDT",
        "n_trades": 0,
        "expectancy": 0.0,
        "win_rate": 0.0,
        "total_pnl": 0.0,
        "final_equity": cfg.initial_capital_usdt,
        "max_drawdown": 0.0,
        "trades": [],
        "hard_reject": [reason],
        "config": asdict(cfg),
        "signal_path": "feature_snapshot",
    }
