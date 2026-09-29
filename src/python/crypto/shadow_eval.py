"""P3 shadow evaluation — SMA20 reference vs one shadow scorer.

Both paths: FeatureSnapshot → scorer → evaluator (NEXT_BAR_OPEN SSOT).
Shadow remains RESEARCH / SHADOW — never auto paper-eligible.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from src.python.crypto.config import assert_crypto_paper_only
from src.python.crypto.evaluator import (
    CryptoEvaluatorConfig,
    backtest_crypto,
    build_evidence_package,
)
from src.python.crypto.features import build_crypto_features
from src.python.crypto.promotion_gate import CryptoPromotionGate
from src.python.crypto.scorer import get_crypto_scorer, is_shadow_scorer

REFERENCE_ID = "crypto_rule_sma20"
SHADOW_ID = "crypto_momentum_shadow"
REFERENCE_VERSION = "crypto_sma_v0"
SHADOW_VERSION = "crypto_mom_v0"


def _signal_fn_for_scorer(strategy_id: str):
    scorer = get_crypto_scorer(strategy_id)

    def _fn(bars: pd.DataFrame) -> pd.DataFrame:
        res = build_crypto_features(bars)
        if res.df.empty:
            return pd.DataFrame(
                columns=["timestamp", "symbol", "side", "confidence", "close"]
            )
        scored = scorer.score_frame(res.df)
        if scored.empty:
            return scored
        if "price" in scored.columns and "close" not in scored.columns:
            scored = scored.rename(columns={"price": "close"})
        return scored

    return _fn


def evaluate_strategy(
    bars: pd.DataFrame,
    strategy_id: str,
    *,
    strategy_version: str,
    cfg: Optional[CryptoEvaluatorConfig] = None,
) -> dict[str, Any]:
    assert_crypto_paper_only()
    cfg = cfg or CryptoEvaluatorConfig()
    sig_fn = _signal_fn_for_scorer(strategy_id)
    bt = backtest_crypto(bars, cfg=cfg, signal_fn=sig_fn)
    wf = _walk_forward_with_signal(bars, cfg=cfg, signal_fn=sig_fn, strategy_id=strategy_id)
    ev = build_evidence_package(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        backtest=bt,
        walk_forward=wf,
    )
    if isinstance(ev.get("walk_forward"), dict) and isinstance(wf, dict):
        ev["walk_forward"] = {
            **ev["walk_forward"],
            **{k: wf[k] for k in ("fold_consistency", "windows") if k in wf},
        }
    ev["plane"] = "SHADOW" if is_shadow_scorer(strategy_id) else "REFERENCE"
    ev["execution_policy"] = bt.get("execution_policy")
    ev["execution_resolver"] = bt.get("execution_resolver")
    return {"backtest": bt, "walk_forward": wf, "evidence": ev}


def _walk_forward_with_signal(
    bars: pd.DataFrame,
    *,
    cfg: CryptoEvaluatorConfig,
    signal_fn,
    strategy_id: str,
) -> dict[str, Any]:
    import numpy as np

    if bars is None or bars.empty:
        return {"windows": [], "n_windows": 0, "live_execution": False, "strategy_id": strategy_id}
    df = bars.sort_values("timestamp").reset_index(drop=True)
    ts = sorted(df["timestamp"].unique())
    windows: list[dict] = []
    i = 0
    while i + cfg.wf_train_bars + cfg.wf_test_bars <= len(ts):
        test_ts = set(ts[i + cfg.wf_train_bars : i + cfg.wf_train_bars + cfg.wf_test_bars])
        window_bars = df[df["timestamp"].isin(test_ts)]
        res = backtest_crypto(window_bars, cfg=cfg, signal_fn=signal_fn)
        windows.append(
            {
                "train_start": str(ts[i]),
                "test_start": str(ts[i + cfg.wf_train_bars]),
                "n_trades": res["n_trades"],
                "expectancy": res["expectancy"],
                "max_drawdown": res["max_drawdown"],
                "total_pnl": res["total_pnl"],
                "win_rate": res.get("win_rate"),
            }
        )
        i += cfg.wf_step_bars
    n_tr = sum(w["n_trades"] for w in windows)
    # VALID folds only: trade_count > 0. Zero-trade folds = insufficient evidence, not neutral.
    valid = [w for w in windows if int(w.get("n_trades") or 0) > 0]
    zero_trade = [w for w in windows if int(w.get("n_trades") or 0) <= 0]
    exp = float(np.mean([w["expectancy"] for w in valid])) if valid else 0.0
    mdd = float(np.max([w["max_drawdown"] for w in valid])) if valid else 0.0
    pos_folds = sum(1 for w in valid if float(w.get("expectancy") or 0) > 0)
    return {
        "plane": "CRYPTO_RESEARCH",
        "live_execution": False,
        "strategy_id": strategy_id,
        "n_windows": len(windows),
        "n_trades": n_tr,
        "expectancy": exp,
        "max_drawdown": mdd,
        "windows": windows,
        "fold_consistency": {
            "n_folds": len(windows),
            "n_valid_folds": len(valid),
            "n_zero_trade_folds": len(zero_trade),
            "positive_expectancy_folds": pos_folds,
            "positive_fold_ratio": (pos_folds / len(valid)) if valid else None,
            "worst_fold_expectancy": float(min((w["expectancy"] for w in valid), default=0.0))
            if valid
            else None,
            "worst_fold_drawdown": float(max((w["max_drawdown"] for w in valid), default=0.0))
            if valid
            else None,
            "definition": "positive_fold_ratio = positive_expectancy / valid_folds; zero-trade excluded",
        },
        "execution_policy": "NEXT_BAR_OPEN",
        "execution_resolver": "crypto.execution.resolve_next_bar_open_fill",
    }


def run_shadow_comparison(
    bars: pd.DataFrame,
    *,
    cfg: Optional[CryptoEvaluatorConfig] = None,
    persist_gate: bool = False,
    status_path: Optional[str] = None,
) -> dict[str, Any]:
    assert_crypto_paper_only()
    cfg = cfg or CryptoEvaluatorConfig(min_trades=5)

    ref = evaluate_strategy(
        bars, REFERENCE_ID, strategy_version=REFERENCE_VERSION, cfg=cfg
    )
    sh = evaluate_strategy(
        bars, SHADOW_ID, strategy_version=SHADOW_VERSION, cfg=cfg
    )

    gate = CryptoPromotionGate()
    shadow_dec = gate.evaluate(
        strategy_id=SHADOW_ID,
        strategy_version=SHADOW_VERSION,
        evidence=sh["evidence"],
        min_trades=cfg.min_trades,
        promote_to_paper_allowed=False,
        persist=persist_gate,
        status_path=status_path,
    )
    ref_dec = gate.evaluate(
        strategy_id=REFERENCE_ID,
        strategy_version=REFERENCE_VERSION,
        evidence=ref["evidence"],
        min_trades=cfg.min_trades,
        promote_to_paper_allowed=False,
        persist=persist_gate,
        status_path=status_path,
    )

    ref_exp = float(ref["backtest"].get("expectancy") or 0.0)
    sh_exp = float(sh["backtest"].get("expectancy") or 0.0)
    return {
        "domain": "CRYPTO",
        "live_execution": False,
        "reference": {
            "strategy_id": REFERENCE_ID,
            "strategy_version": REFERENCE_VERSION,
            "evidence": ref["evidence"],
            "gate": ref_dec.to_dict(),
        },
        "shadow": {
            "strategy_id": SHADOW_ID,
            "strategy_version": SHADOW_VERSION,
            "plane": "SHADOW",
            "evidence": sh["evidence"],
            "gate": shadow_dec.to_dict(),
            "paper_eligible": False,
        },
        "comparison": {
            "shadow_expectancy": sh_exp,
            "reference_expectancy": ref_exp,
            "delta_expectancy": sh_exp - ref_exp,
            "shadow_n_trades": int(sh["backtest"].get("n_trades") or 0),
            "reference_n_trades": int(ref["backtest"].get("n_trades") or 0),
            "shadow_beats_reference": sh_exp > ref_exp
            and int(sh["backtest"].get("n_trades") or 0) >= cfg.min_trades,
        },
        "invariants": {
            "shadow_auto_paper_allowed": False,
            "shared_execution_resolver": "crypto.execution.resolve_next_bar_open_fill",
            "feature_ssot": "CryptoFeatureSnapshot",
            "idx_touched": False,
        },
    }
