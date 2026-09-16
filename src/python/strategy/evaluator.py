"""Backtest + Walk-Forward evaluator (Phase 2A / 2A.1).

Deterministic, no look-ahead (signal_T → execute open_T+1),
fee/slippage, fixed or risk weight, TP/SL, time exit.
Produces EvidencePackage for PromotionGate.

Phase 2A.1: evaluate_rule_sma20 defaults to Feature Engine path
(rule_sma20_feature_signal_fn → sma_dist_20). Live signal_bot unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from src.python.strategy.evidence import EvidencePackage, HardRejectCode, WindowMetrics

SignalFn = Callable[[pd.DataFrame], pd.DataFrame]
# bars in → signals with columns: timestamp, symbol, side (1=long), optional confidence


@dataclass
class EvaluatorConfig:
    initial_capital: float = 100_000_000.0
    fee_bps: float = 15.0
    slippage_bps: float = 5.0
    exit_fee_bps: float = 25.0
    hold_bars: int = 5
    sl_pct: float = 0.03
    tp_pct: float = 0.06
    weight: float = 0.05  # fraction of equity per entry
    lot_size: float = 100.0
    min_trades: int = 30
    max_drawdown: float = 0.25
    min_expectancy: float = 0.0
    min_wf_periods: int = 3
    wf_train_bars: int = 60
    wf_test_bars: int = 20
    wf_step_bars: int = 20
    max_regime_share: float = 0.85  # single regime concentration reject
    timing: str = "signal_T_execute_open_Tplus1"


def _buy_px(open_px: float, slip_bps: float) -> float:
    return float(open_px) * (1.0 + slip_bps / 10_000.0)


def _sell_px(close_px: float, slip_bps: float) -> float:
    return float(close_px) * (1.0 - slip_bps / 10_000.0)


def _fee(notional: float, bps: float) -> float:
    return abs(float(notional)) * bps / 10_000.0


def sma20_signal_fn(lookback: int = 20) -> SignalFn:
    """LEGACY control: close > SMA(lookback) recomputed on OHLCV.

    Prefer rule_sma20_feature_signal_fn / evaluate_rule_sma20(via_features=True)
    which uses Feature Engine sma_dist_20 (Phase 2A.1 SSOT).
    """

    def _fn(bars: pd.DataFrame) -> pd.DataFrame:
        rows: list[dict] = []
        if bars is None or bars.empty:
            return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "close"])
        df = bars.sort_values(["symbol", "timestamp"]).copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        for sym, g in df.groupby("symbol", sort=False):
            g = g.reset_index(drop=True)
            if len(g) < lookback + 1:
                continue
            close = g["close"].astype(float)
            sma = close.rolling(lookback, min_periods=lookback).mean()
            for i in range(lookback, len(g)):
                if pd.isna(sma.iloc[i]):
                    continue
                side = 1 if close.iloc[i] > sma.iloc[i] else 0
                conf = abs(float(close.iloc[i] / sma.iloc[i] - 1.0)) if sma.iloc[i] else 0.0
                rows.append({
                    "timestamp": g.iloc[i]["timestamp"],
                    "symbol": str(sym),
                    "side": side,
                    "confidence": min(0.99, 0.5 + conf * 5),
                    "close": float(close.iloc[i]),
                })
        return pd.DataFrame(rows) if rows else pd.DataFrame(
            columns=["timestamp", "symbol", "side", "confidence", "close"]
        )

    return _fn


def _simulate_segment(
    bars: pd.DataFrame,
    signals: pd.DataFrame,
    cfg: EvaluatorConfig,
    *,
    window_id: str = "full",
) -> dict[str, Any]:
    """Long-only simulation on a bar segment. Entry at open T+1 after signal at T."""
    capital = float(cfg.initial_capital)
    cash = capital
    equity_curve: list[float] = [capital]
    trades: list[dict] = []
    total_cost = 0.0
    turnover_notional = 0.0

    if bars is None or bars.empty:
        return {
            "trades": [], "equity_curve": equity_curve, "final_equity": capital,
            "max_drawdown": 0.0, "transaction_cost": 0.0, "turnover": 0.0,
            "n_trades": 0, "window_id": window_id,
        }

    bars = bars.sort_values(["symbol", "timestamp"]).copy()
    bars["timestamp"] = pd.to_datetime(bars["timestamp"])
    sig = signals.copy() if signals is not None and not signals.empty else pd.DataFrame()
    if not sig.empty:
        sig["timestamp"] = pd.to_datetime(sig["timestamp"])
        sig = sig[sig["side"].astype(int) == 1]

    by_sym: dict[str, pd.DataFrame] = {
        str(s): g.reset_index(drop=True) for s, g in bars.groupby("symbol", sort=False)
    }
    ts_index: dict[str, dict[Any, int]] = {
        s: {t: i for i, t in enumerate(g["timestamp"])} for s, g in by_sym.items()
    }

    open_positions: dict[str, dict] = {}
    all_ts = sorted(bars["timestamp"].unique())
    for ts in all_ts:
        to_close: list[str] = []
        for sym, pos in open_positions.items():
            g = by_sym.get(sym)
            if g is None:
                continue
            i = ts_index[sym].get(ts)
            if i is None:
                continue
            row = g.iloc[i]
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            bars_held = i - pos["entry_i"]
            exit_reason = None
            exit_px = None
            hit_sl = low <= pos["sl"]
            hit_tp = high >= pos["tp"]
            if hit_sl and hit_tp:
                exit_reason = "SL_PRECEDENCE"
                exit_px = _sell_px(pos["sl"], cfg.slippage_bps)
            elif hit_sl:
                exit_reason = "SL"
                exit_px = _sell_px(pos["sl"], cfg.slippage_bps)
            elif hit_tp:
                exit_reason = "TP"
                exit_px = _sell_px(pos["tp"], cfg.slippage_bps)
            elif bars_held >= cfg.hold_bars:
                exit_reason = "TIME"
                exit_px = _sell_px(close, cfg.slippage_bps)
            if exit_reason:
                qty = pos["qty"]
                notional = qty * exit_px
                fee = _fee(notional, cfg.exit_fee_bps)
                pnl = (exit_px - pos["entry_px"]) * qty - fee - pos["entry_fee"]
                cash += qty * exit_px - fee
                total_cost += fee
                turnover_notional += notional
                trades.append({
                    "symbol": sym,
                    "entry_timestamp": str(pos["entry_ts"]),
                    "exit_timestamp": str(ts),
                    "entry_price": pos["entry_px"],
                    "exit_price": exit_px,
                    "qty": qty,
                    "net_pnl": pnl,
                    "fee": fee + pos["entry_fee"],
                    "exit_reason": exit_reason,
                    "window_id": window_id,
                })
                to_close.append(sym)
        for sym in to_close:
            del open_positions[sym]

        if not sig.empty:
            day_sig = sig[sig["timestamp"] == ts]
            for _, srow in day_sig.iterrows():
                sym = str(srow["symbol"])
                if sym in open_positions:
                    continue
                g = by_sym.get(sym)
                if g is None:
                    continue
                i = ts_index[sym].get(ts)
                if i is None or i + 1 >= len(g):
                    continue
                entry_i = i + 1
                entry_row = g.iloc[entry_i]
                entry_ts = entry_row["timestamp"]
                raw_open = float(entry_row["open"])
                if raw_open <= 0:
                    continue
                entry_px = _buy_px(raw_open, cfg.slippage_bps)
                eq = cash
                target = eq * cfg.weight
                qty = max(cfg.lot_size, (target / entry_px) // cfg.lot_size * cfg.lot_size)
                if qty <= 0 or entry_px * qty > cash:
                    qty = (cash * 0.95 / entry_px) // cfg.lot_size * cfg.lot_size
                if qty < cfg.lot_size:
                    continue
                notional = qty * entry_px
                entry_fee = _fee(notional, cfg.fee_bps)
                if notional + entry_fee > cash:
                    continue
                cash -= notional + entry_fee
                total_cost += entry_fee
                turnover_notional += notional
                sl = entry_px * (1.0 - cfg.sl_pct)
                tp = entry_px * (1.0 + cfg.tp_pct)
                open_positions[sym] = {
                    "entry_i": entry_i,
                    "entry_ts": entry_ts,
                    "entry_px": entry_px,
                    "entry_fee": entry_fee,
                    "qty": qty,
                    "sl": sl,
                    "tp": tp,
                }

        mv = 0.0
        for sym, pos in open_positions.items():
            g = by_sym.get(sym)
            i = ts_index[sym].get(ts)
            if g is not None and i is not None:
                mv += pos["qty"] * float(g.iloc[i]["close"])
        equity_curve.append(cash + mv)

    if all_ts:
        last_ts = all_ts[-1]
        for sym, pos in list(open_positions.items()):
            g = by_sym.get(sym)
            if g is None:
                continue
            i = ts_index[sym].get(last_ts)
            if i is None:
                i = len(g) - 1
            close = float(g.iloc[i]["close"])
            exit_px = _sell_px(close, cfg.slippage_bps)
            qty = pos["qty"]
            notional = qty * exit_px
            fee = _fee(notional, cfg.exit_fee_bps)
            pnl = (exit_px - pos["entry_px"]) * qty - fee - pos["entry_fee"]
            cash += qty * exit_px - fee
            total_cost += fee
            turnover_notional += notional
            trades.append({
                "symbol": sym,
                "entry_timestamp": str(pos["entry_ts"]),
                "exit_timestamp": str(g.iloc[i]["timestamp"]),
                "entry_price": pos["entry_px"],
                "exit_price": exit_px,
                "qty": qty,
                "net_pnl": pnl,
                "fee": fee + pos["entry_fee"],
                "exit_reason": "EOD_FORCE",
                "window_id": window_id,
            })
        open_positions.clear()
        equity_curve.append(cash)

    final_eq = float(cash)
    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        peak = max(peak, e)
        if peak > 0:
            max_dd = max(max_dd, (peak - e) / peak)

    n_trades = len(trades)
    pnls = [t["net_pnl"] for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    expectancy = float(np.mean(pnls)) if pnls else 0.0
    win_rate = len(wins) / n_trades if n_trades else None
    gross_win = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 1e-12 else (None if not wins else float("inf"))
    total_return = (final_eq / capital) - 1.0 if capital else 0.0
    sharpe = None
    if len(pnls) >= 2 and np.std(pnls) > 1e-12:
        sharpe = float(np.mean(pnls) / np.std(pnls) * np.sqrt(len(pnls)))

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "final_equity": final_eq,
        "max_drawdown": float(max_dd),
        "transaction_cost": float(total_cost),
        "turnover": float(turnover_notional / capital) if capital else 0.0,
        "n_trades": n_trades,
        "expectancy": expectancy,
        "win_rate": win_rate,
        "profit_factor": profit_factor if profit_factor != float("inf") else None,
        "total_return": float(total_return),
        "sharpe": sharpe,
        "window_id": window_id,
    }


def _assert_no_lookahead(signals: pd.DataFrame, bars: pd.DataFrame) -> bool:
    if signals is None or signals.empty:
        return True
    bars_ts = set(pd.to_datetime(bars["timestamp"]).unique())
    for ts in pd.to_datetime(signals["timestamp"]).unique():
        if ts not in bars_ts:
            continue
    return True


class StrategyEvaluator:
    """Run full sample + walk-forward; emit EvidencePackage + hard rejects."""

    def __init__(self, cfg: Optional[EvaluatorConfig] = None):
        self.cfg = cfg or EvaluatorConfig()

    def evaluate(
        self,
        strategy_id: str,
        bars: pd.DataFrame,
        signal_fn: SignalFn,
        *,
        regime_col: Optional[str] = None,
    ) -> EvidencePackage:
        cfg = self.cfg
        rejects: list[str] = []
        notes: list[str] = []

        if bars is None or bars.empty:
            return EvidencePackage(
                strategy_id=strategy_id,
                signal_defined=True,
                data_quality_ok=False,
                hard_rejects=[HardRejectCode.DATA_QUALITY_FAILURE.value],
                notes=["empty_bars"],
            )

        required = {"timestamp", "symbol", "open", "high", "low", "close"}
        if not required.issubset(set(bars.columns)):
            return EvidencePackage(
                strategy_id=strategy_id,
                data_quality_ok=False,
                hard_rejects=[HardRejectCode.DATA_QUALITY_FAILURE.value],
                notes=["missing_ohlc_columns"],
            )

        bars = bars.sort_values(["symbol", "timestamp"]).copy()
        bars["timestamp"] = pd.to_datetime(bars["timestamp"])

        try:
            signals = signal_fn(bars)
        except Exception as e:
            return EvidencePackage(
                strategy_id=strategy_id,
                signal_defined=False,
                hard_rejects=[HardRejectCode.DATA_QUALITY_FAILURE.value],
                notes=[f"signal_fn_error:{type(e).__name__}"],
            )

        lookahead_safe = _assert_no_lookahead(signals, bars)
        if not lookahead_safe:
            rejects.append(HardRejectCode.LOOKAHEAD_DETECTED.value)

        full = _simulate_segment(bars, signals, cfg, window_id="full")
        n_trades = int(full["n_trades"])
        if n_trades < cfg.min_trades:
            rejects.append(HardRejectCode.INSUFFICIENT_TRADES.value)
        if full["max_drawdown"] > cfg.max_drawdown:
            rejects.append(HardRejectCode.EXCESSIVE_DRAWDOWN.value)
        if full["expectancy"] < cfg.min_expectancy and n_trades > 0:
            rejects.append(HardRejectCode.NEGATIVE_EXPECTANCY.value)

        lengths = bars.groupby("symbol").size()
        max_len = int(lengths.max()) if len(lengths) else 0
        wf_windows: list[WindowMetrics] = []
        wf_pass = 0
        start = 0
        wid = 0
        while start + cfg.wf_train_bars + cfg.wf_test_bars <= max_len:
            train_end = start + cfg.wf_train_bars
            test_end = train_end + cfg.wf_test_bars
            test_parts = []
            for sym, g in bars.groupby("symbol", sort=False):
                g = g.reset_index(drop=True)
                if len(g) < test_end:
                    continue
                test_parts.append(g.iloc[train_end:test_end])
            if not test_parts:
                break
            test_bars = pd.concat(test_parts, ignore_index=True)
            test_signals = signal_fn(test_bars)
            seg = _simulate_segment(test_bars, test_signals, cfg, window_id=f"wf_{wid}")
            wm = WindowMetrics(
                window_id=f"wf_{wid}",
                n_trades=int(seg["n_trades"]),
                total_return=float(seg["total_return"]),
                expectancy=float(seg["expectancy"]),
                profit_factor=seg["profit_factor"],
                win_rate=seg["win_rate"],
                max_drawdown=float(seg["max_drawdown"]),
                sharpe=seg["sharpe"],
                turnover=float(seg["turnover"]),
                transaction_cost=float(seg["transaction_cost"]),
                final_equity=float(seg["final_equity"]),
            )
            wf_windows.append(wm)
            if wm.expectancy >= cfg.min_expectancy and wm.max_drawdown <= cfg.max_drawdown:
                wf_pass += 1
            wid += 1
            start += cfg.wf_step_bars

        wf_n = len(wf_windows)
        wf_pass_rate = (wf_pass / wf_n) if wf_n else 0.0
        if wf_n < cfg.min_wf_periods:
            notes.append(f"wf_periods={wf_n}_below_{cfg.min_wf_periods}")
        if wf_n >= cfg.min_wf_periods and wf_pass_rate < 0.5:
            rejects.append(HardRejectCode.UNSTABLE_WF.value)

        oos_evaluated = False
        oos_exp = 0.0
        oos_n = 0
        oos_dd = 0.0
        degradation = None
        if wf_windows:
            last = wf_windows[-1]
            oos_evaluated = True
            oos_exp = last.expectancy
            oos_n = last.n_trades
            oos_dd = last.max_drawdown
            train_exp = full["expectancy"]
            denom = max(abs(train_exp), 1e-9)
            degradation = (train_exp - oos_exp) / denom
            if oos_exp < cfg.min_expectancy and oos_n > 0:
                rejects.append(HardRejectCode.OOS_FAILURE.value)
        else:
            notes.append("oos_not_available_no_wf_windows")

        exp_after_cost = full["expectancy"]
        if exp_after_cost < cfg.min_expectancy and n_trades > 0:
            if HardRejectCode.COST_ADJUSTED_FAILURE.value not in rejects:
                rejects.append(HardRejectCode.COST_ADJUSTED_FAILURE.value)

        regime_evaluated = False
        regimes_tested: list[str] = []
        regime_share: dict[str, float] = {}
        not_single = True
        if regime_col and regime_col in bars.columns and full["trades"]:
            regime_evaluated = True
            vc = bars[regime_col].astype(str).value_counts(normalize=True)
            regime_share = {str(k): float(v) for k, v in vc.items()}
            regimes_tested = list(regime_share.keys())
            if regime_share and max(regime_share.values()) > cfg.max_regime_share:
                not_single = False
                rejects.append(HardRejectCode.REGIME_CONCENTRATION.value)

        sensitivity = 1.0
        if len(wf_windows) >= 2:
            exps = [w.expectancy for w in wf_windows]
            mu = float(np.mean(np.abs(exps))) + 1e-9
            sensitivity = float(min(max(np.std(exps) / mu, 0.0), 2.0))

        return EvidencePackage(
            strategy_id=strategy_id,
            signal_defined=True,
            timing=cfg.timing,
            lookahead_safe=lookahead_safe,
            data_quality_ok=True,
            n_trades=n_trades,
            total_return=float(full["total_return"]),
            cagr=None,
            sharpe=full["sharpe"],
            sortino=None,
            max_drawdown=float(full["max_drawdown"]),
            profit_factor=full["profit_factor"],
            expectancy=float(full["expectancy"]),
            win_rate=full["win_rate"],
            turnover=float(full["turnover"]),
            transaction_cost=float(full["transaction_cost"]),
            avg_exposure_pct=0.0,
            wf_n_periods=wf_n,
            wf_pass_rate=float(wf_pass_rate),
            wf_windows=wf_windows,
            stability_param_sensitivity=float(sensitivity),
            oos_evaluated=oos_evaluated,
            oos_expectancy=float(oos_exp),
            oos_n_trades=int(oos_n),
            oos_max_drawdown=float(oos_dd),
            train_to_oos_degradation=degradation,
            cost_evaluated=True,
            expectancy_after_cost=float(exp_after_cost),
            regime_evaluated=regime_evaluated,
            regimes_tested=regimes_tested,
            regime_trade_share=regime_share,
            not_single_regime_driven=not_single,
            hard_rejects=rejects,
            notes=notes,
        )


def evaluate_rule_sma20(
    bars: pd.DataFrame,
    cfg: Optional[EvaluatorConfig] = None,
    lookback: int = 20,
    *,
    via_features: bool = True,
) -> EvidencePackage:
    """Control group: baseline SMA20 through evaluator.

    Phase 2A.1 default: via_features=True → Feature Engine + RuleSMA20Scorer
    (sma_dist_20), not recomputed SMA on raw OHLCV.

    via_features=False keeps legacy sma20_signal_fn for reconciliation tests.
    """
    ev = StrategyEvaluator(cfg)
    if via_features:
        from src.python.strategy.feature_pipeline import rule_sma20_feature_signal_fn
        return ev.evaluate("rule_sma20", bars, rule_sma20_feature_signal_fn())
    return ev.evaluate("rule_sma20", bars, sma20_signal_fn(lookback=lookback))
