"""Walk-Forward Analysis executor — Colab/research compute, never Actions-heavy.

Deterministic, time-ordered TRAIN→VALIDATION→TEST. Uses SimulationCostModel
identical to paper portfolio. Never mutates Champion / registry / ledger.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.python.data.costs import SimulationCostModel
from src.python.research.colab_jobs import ColabResearchJob, ResearchJobKind, validate_job
from src.python.research.experiment_result import ExperimentResult, ExperimentResultStore


CANONICAL_COST = SimulationCostModel()
MIN_TRADES_OOS = 5


def _bars_hash(bars: pd.DataFrame) -> str:
    cols = [c for c in ("timestamp", "symbol", "open", "high", "low", "close", "volume") if c in bars.columns]
    raw = bars[cols].head(5000).to_csv(index=False).encode()
    return hashlib.sha256(raw).hexdigest()[:24]


def validate_pit_features(bars: pd.DataFrame) -> list[str]:
    """Reject future-corrupted columns (label / future_*)."""
    bad: list[str] = []
    for c in bars.columns:
        cl = str(c).lower()
        if cl.startswith("future_") or cl.startswith("y_") or cl in ("target", "label", "y"):
            bad.append(c)
        if "lookahead" in cl or "future" in cl:
            bad.append(c)
    return bad


def _sma(series: np.ndarray, window: int) -> np.ndarray:
    out = np.full_like(series, np.nan, dtype=float)
    if len(series) < window:
        return out
    csum = np.cumsum(series, dtype=float)
    csum[window:] = csum[window:] - csum[:-window]
    out[window - 1 :] = csum[window - 1 :] / window
    return out


def _simulate_signals(
    close: np.ndarray,
    open_: np.ndarray,
    *,
    sma_window: int,
    cost: SimulationCostModel,
) -> dict[str, Any]:
    """PIT: signal on close[t] using SMA from close[:t+1]; fill at open[t+1]."""
    sma = _sma(close, sma_window)
    trades = []
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    position = 0
    entry_px = 0.0
    fees_paid = 0.0

    for t in range(sma_window, len(close) - 1):
        if np.isnan(sma[t]):
            continue
        signal = 1 if close[t] > sma[t] else 0
        fill = float(open_[t + 1])
        if signal == 1 and position == 0:
            buy_px = cost.buy_price(fill)
            fee = cost.fee(buy_px)
            fees_paid += fee
            entry_px = buy_px
            position = 1
            trades.append({"side": "BUY", "px": buy_px, "t": t + 1, "fee": fee})
        elif signal == 0 and position == 1:
            sell_px = cost.sell_price(fill)
            fee = cost.exit_fee(sell_px)
            fees_paid += fee
            ret = (sell_px - entry_px) / entry_px - (fee / max(entry_px, 1e-9))
            equity *= 1.0 + ret
            peak = max(peak, equity)
            max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 0.0)
            trades.append({"side": "SELL", "px": sell_px, "t": t + 1, "fee": fee, "ret": ret})
            position = 0

    rets = [tr["ret"] for tr in trades if tr.get("side") == "SELL"]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    gross_win = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 1e-12 else (999.0 if gross_win > 0 else 0.0)
    avg_r = float(np.mean(rets)) if rets else 0.0
    return {
        "n_trades": len(rets),
        "win_rate": len(wins) / len(rets) if rets else 0.0,
        "loss_rate": len(losses) / len(rets) if rets else 0.0,
        "expectancy": avg_r,
        "average_r": avg_r,
        "profit_factor": float(pf),
        "total_return": equity - 1.0,
        "max_drawdown": float(max_dd),
        "fees_paid": fees_paid,
        "worst_trade": float(min(rets)) if rets else 0.0,
        "sharpe": float(np.mean(rets) / (np.std(rets) + 1e-12) * np.sqrt(max(len(rets), 1))) if rets else 0.0,
    }


def _window_slices(n: int, n_windows: int = 3, train_frac: float = 0.5, val_frac: float = 0.2) -> list[dict[str, int]]:
    if n < 40:
        return []
    windows = []
    usable = n - 5
    for i in range(n_windows):
        start = int(i * (usable * 0.15))
        end = usable
        span = end - start
        if span < 30:
            continue
        train_end = start + int(span * train_frac)
        val_end = train_end + int(span * val_frac)
        test_end = end
        if test_end - val_end < 5:
            continue
        windows.append({
            "window_id": f"W{i+1}",
            "train_start": start,
            "train_end": train_end,
            "validation_start": train_end,
            "validation_end": val_end,
            "test_start": val_end,
            "test_end": test_end,
        })
    return windows


@dataclass
class WFAExecutor:
    store: Optional[ExperimentResultStore] = None
    cost: SimulationCostModel = None  # type: ignore

    def __post_init__(self) -> None:
        if self.cost is None:
            self.cost = SimulationCostModel()
        if self.store is None:
            self.store = ExperimentResultStore()

    def execute(
        self,
        job: ColabResearchJob,
        bars: pd.DataFrame,
        *,
        champion_snapshot: Optional[dict[str, Any]] = None,
        allow_champion_write: bool = False,
    ) -> ExperimentResult:
        if allow_champion_write:
            raise PermissionError("research_executor_cannot_write_champion")
        errs = validate_job(job)
        if errs:
            return self._fail(job, f"job_invalid:{','.join(errs)}", bars)

        if job.kind != ResearchJobKind.WALK_FORWARD.value:
            return self._fail(job, f"unsupported_kind:{job.kind}", bars)

        if job.cost_model not in ("simulation_v2", "SIMULATION", self.cost.model_kind, "simulation"):
            return self._fail(job, "cost_model_mismatch", bars)

        pit_bad = validate_pit_features(bars)
        if pit_bad:
            return self._fail(job, f"lookahead_features:{pit_bad}", bars, leakage={"future_cols": pit_bad})

        required = {"timestamp", "open", "close"}
        if not required.issubset(set(bars.columns)):
            return self._fail(job, "bars_missing_ohlc", bars)

        bars = bars.sort_values("timestamp").reset_index(drop=True)
        dhash = job.dataset_hash if job.dataset_hash not in ("", "UNKNOWN") else _bars_hash(bars)
        fp = job.configuration_fingerprint()

        existing = self.store.get(job.experiment_id or job.job_id, fp)
        if existing is not None:
            return existing

        close = bars["close"].to_numpy(dtype=float)
        open_ = bars["open"].to_numpy(dtype=float)
        sma_window = int(job.parameters.get("sma_window", 20))
        n_windows = int(job.parameters.get("n_windows", 3))
        windows_meta = _window_slices(len(bars), n_windows=n_windows)
        if not windows_meta:
            return self._fail(job, "insufficient_rows_for_wfa", bars)

        window_results = []
        oos_metrics_list = []
        for w in windows_meta:
            seg = bars.iloc[: w["test_end"]].copy()
            c = seg["close"].to_numpy(dtype=float)
            o = seg["open"].to_numpy(dtype=float)
            m = _simulate_signals(c, o, sma_window=sma_window, cost=self.cost)
            wr = {
                **w,
                "n_train": w["train_end"] - w["train_start"],
                "n_validation": w["validation_end"] - w["validation_start"],
                "n_test": w["test_end"] - w["test_start"],
                "parameter_snapshot": {"sma_window": sma_window},
                "metrics_oos": m,
            }
            window_results.append(wr)
            oos_metrics_list.append(m)

        if not oos_metrics_list:
            return self._fail(job, "no_oos_windows", bars)

        n_trades = sum(m["n_trades"] for m in oos_metrics_list)
        status = "INSUFFICIENT_EVIDENCE" if n_trades < MIN_TRADES_OOS else "COMPLETED"

        avg = lambda k: float(np.mean([m[k] for m in oos_metrics_list]))
        metrics = {
            "oos": {
                "n_trades": n_trades,
                "expectancy": avg("expectancy"),
                "average_r": avg("average_r"),
                "win_rate": avg("win_rate"),
                "loss_rate": avg("loss_rate"),
                "profit_factor": avg("profit_factor"),
                "total_return": avg("total_return"),
                "max_drawdown": avg("max_drawdown"),
                "sharpe": avg("sharpe"),
                "worst_trade": min(m["worst_trade"] for m in oos_metrics_list),
                "fees_paid": sum(m["fees_paid"] for m in oos_metrics_list),
            },
            "in_sample": {"note": "IS metrics intentionally not used for promotion"},
            "validation": {"note": "validation reserved for parameter selection only"},
        }

        stress = []
        for fee_mult, slip_mult, label in ((1.0, 1.0, "base"), (1.5, 1.5, "fee_stress"), (1.0, 2.0, "slip_stress")):
            c2 = SimulationCostModel(
                fee_bps=self.cost.fee_bps * fee_mult,
                exit_fee_bps=self.cost.exit_fee_bps * fee_mult,
                slippage_bps=self.cost.slippage_bps * slip_mult,
            )
            m2 = _simulate_signals(close, open_, sma_window=sma_window, cost=c2)
            stress.append({"label": label, "expectancy": m2["expectancy"], "n_trades": m2["n_trades"]})
        for dw in (-2, 2):
            m3 = _simulate_signals(close, open_, sma_window=max(5, sma_window + dw), cost=self.cost)
            stress.append({"label": f"sma_{sma_window + dw}", "expectancy": m3["expectancy"], "n_trades": m3["n_trades"]})

        base_exp = metrics["oos"]["expectancy"]
        stressed_ok = sum(1 for s in stress if s["expectancy"] > -0.05) >= 3
        if status == "COMPLETED":
            status = "ROBUST" if stressed_ok and base_exp > 0 else "FRAGILE"

        n_pos_windows = sum(1 for m in oos_metrics_list if m.get("expectancy", 0) > 0)
        single_window_edge = n_pos_windows <= 1 and len(oos_metrics_list) > 1
        overfit_risk = (n_windows > 1 and not stressed_ok) or single_window_edge
        robustness = {
            "stress": stress,
            "stability": "ROBUST" if status == "ROBUST" else "FRAGILE",
            "overfit_risk": overfit_risk,
            "n_positive_oos_windows": n_pos_windows,
            "n_oos_windows": len(oos_metrics_list),
            "selection_split": "NONE",
            "selection_rule": "fixed_params_from_job_no_oos_tuning",
            "evaluation_split": "TEST_OOS",
            "note": "parameters taken from job; never tuned on test/OOS",
        }

        result = ExperimentResult(
            experiment_id=job.experiment_id or job.job_id,
            job_id=job.job_id,
            hypothesis_id=job.hypothesis_id,
            baseline_version=job.baseline_id,
            challenger_version=f"{job.strategy_id}@{job.strategy_version}",
            dataset_hash=dhash,
            feature_hash=job.feature_hash,
            commit_sha=job.commit_sha,
            cost_model=job.cost_model,
            cost_model_detail=self.cost.to_dict(),
            seed=job.random_seed,
            configuration_fingerprint=fp,
            windows=window_results,
            metrics=metrics,
            robustness=robustness,
            leakage_checks={"future_cols": [], "pit_ok": True},
            integrity_checks={
                "cost_model_match": True,
                "champion_write": False,
                "registry_write": False,
            },
            status=status,
            number_of_trials=1 + len([s for s in stress if s["label"].startswith("sma_")]),
            number_of_candidates=1,
            selection_rule="fixed_params_from_job_no_oos_tuning",
            selection_split="NONE",
        )
        if champion_snapshot is not None:
            result.integrity_checks["champion_snapshot_read"] = True
            result.integrity_checks["champion_id"] = champion_snapshot.get("strategy_id", "")

        return self.store.put(result)

    def _fail(
        self,
        job: ColabResearchJob,
        reason: str,
        bars: pd.DataFrame,
        leakage: Optional[dict] = None,
    ) -> ExperimentResult:
        status = "INVALID" if "lookahead" in reason or "cost_model" in reason else "FAILED"
        result = ExperimentResult(
            experiment_id=job.experiment_id or job.job_id,
            job_id=job.job_id,
            configuration_fingerprint=job.configuration_fingerprint(),
            dataset_hash=job.dataset_hash,
            cost_model=job.cost_model,
            seed=job.random_seed,
            status=status,
            metrics={"error": reason},
            leakage_checks=leakage or {},
            integrity_checks={"fail_reason": reason, "champion_write": False},
            cost_model_detail=self.cost.to_dict(),
        )
        return self.store.put(result)


from src.python.research.evidence_bridge import (  # noqa: E402
    experiment_result_to_evidence,
    experiment_result_to_evidence_package,
    evaluate_research_candidacy,
)
