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
    walk_forward_crypto,
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
    bt = backtest_crypto(bars, cfg=cfg, signal_fn=_signal_fn_for_scorer(strategy_id))
    wf = walk_forward_crypto(bars, cfg=cfg)
    if strategy_id != REFERENCE_ID:
        wf = {
            **wf,
            "note": "WFA_WINDOWS_USE_DEFAULT_SIGNAL; primary_evidence=backtest",
            "strategy_id": strategy_id,
        }
    ev = build_evidence_package(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        backtest=bt,
        walk_forward=wf,
    )
    ev["plane"] = "SHADOW" if is_shadow_scorer(strategy_id) else "REFERENCE"
    ev["execution_policy"] = bt.get("execution_policy")
    ev["execution_resolver"] = bt.get("execution_resolver")
    return {"backtest": bt, "walk_forward": wf, "evidence": ev}


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
