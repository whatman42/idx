"""Production signal path — FeatureSnapshot SSOT + promotion enforcement.

OHLCV → build_features → FeatureSnapshot path → PROMOTED scorers only for fills.
SHADOW/RESEARCH scorers are scored for report comparison only (no fills).

rule_sma20 remains the production baseline until PromotionGate promotes a challenger.
"""
from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from src.python.features.engine import build_features
from src.python.features.tiers import FeatureTier
from src.python.strategy.production_control import (
    assert_production_allowed,
    control_plane_summary,
    eligibility,
    production_strategy_ids,
    shadow_strategy_ids,
)
from src.python.strategy.scorers import get_scorer


def _latest_day(signals: pd.DataFrame) -> pd.DataFrame:
    if signals is None or signals.empty:
        return signals if signals is not None else pd.DataFrame()
    ts = pd.to_datetime(signals["timestamp"])
    last = ts.max().normalize()
    return signals[ts.dt.normalize() == last].copy()


def build_ops_feature_frame(
    bars: pd.DataFrame,
    *,
    max_tier: int = FeatureTier.TIER1_STANDARD,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Single Feature Engine pass — SSOT for ops production + shadow."""
    if bars is None or getattr(bars, "empty", True):
        return pd.DataFrame(), {"ok": False, "reason": "empty_bars"}
    result = build_features(bars, max_tier=max_tier)
    feat = result.df
    drop_cols = [c for c in ("y_next_up", "y") if c in feat.columns]
    if drop_cols:
        feat = feat.drop(columns=drop_cols)
    meta = {
        "ok": not feat.empty,
        "feature_set_version": getattr(result, "feature_set_version", ""),
        "max_tier": max_tier,
        "n_rows": int(len(feat)),
        "n_symbols": int(feat["symbol"].nunique()) if not feat.empty and "symbol" in feat.columns else 0,
        "ssot": "FeatureSnapshot_via_build_features",
    }
    return feat, meta


def score_production(
    feat: pd.DataFrame,
    *,
    strategy_id: str = "rule_sma20",
) -> pd.DataFrame:
    """Score only PROMOTED strategies — hard fail if not eligible."""
    assert_production_allowed(strategy_id)
    if feat is None or feat.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "score", "strategy_id"])
    scorer = get_scorer(strategy_id)
    out = scorer.score_frame(feat)
    if out is None or out.empty:
        return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "score", "strategy_id"])
    out = out.copy()
    out["strategy_id"] = strategy_id
    return out


def score_shadow(
    feat: pd.DataFrame,
    *,
    strategy_ids: Optional[list[str]] = None,
) -> dict[str, pd.DataFrame]:
    """Score RESEARCH/SHADOW strategies for report only — never for fills."""
    ids = strategy_ids if strategy_ids is not None else shadow_strategy_ids()
    preferred = ["trend_multi"]
    ordered = [s for s in preferred if s in ids] + [s for s in ids if s not in preferred]
    ordered = ordered[:3]
    out: dict[str, pd.DataFrame] = {}
    for sid in ordered:
        e = eligibility(sid)
        if not e.shadow_allowed or e.production_allowed:
            continue
        try:
            scorer = get_scorer(sid)
        except Exception:
            continue
        try:
            df = scorer.score_frame(feat)
            if df is not None and not df.empty:
                df = df.copy()
                df["strategy_id"] = sid
                df["path"] = "SHADOW"
                out[sid] = df
        except Exception:
            continue
    return out


def production_signals_from_bars(
    bars: pd.DataFrame,
    *,
    strategy_id: str = "rule_sma20",
    max_tier: int = FeatureTier.TIER1_STANDARD,
    include_shadow: bool = True,
) -> dict[str, Any]:
    """End-to-end ops signal build.

    Returns:
      production_day: latest-day BUY candidates from PROMOTED scorer
      production_all: full scored frame
      shadow: dict strategy_id → scored frame (latest day summary in meta)
      feature_meta / control_plane
    """
    feat, fmeta = build_ops_feature_frame(bars, max_tier=max_tier)
    control = control_plane_summary()
    empty = {
        "production_day": pd.DataFrame(),
        "production_all": pd.DataFrame(),
        "shadow": {},
        "shadow_day_summary": [],
        "feature_meta": fmeta,
        "control_plane": control,
        "strategy_id": strategy_id,
        "path": "FEATURE_SSOT",
    }
    if not fmeta.get("ok"):
        empty["feature_meta"]["reason"] = fmeta.get("reason", "feature_build_failed")
        return empty

    prod_all = score_production(feat, strategy_id=strategy_id)
    prod_day = _latest_day(prod_all)
    if not prod_day.empty and "side" in prod_day.columns:
        prod_day = prod_day[prod_day["side"] == 1].copy()

    shadow_map: dict[str, pd.DataFrame] = {}
    shadow_summary: list[dict[str, Any]] = []
    if include_shadow:
        shadow_map = score_shadow(feat)
        for sid, sdf in shadow_map.items():
            day = _latest_day(sdf)
            n = int(len(day)) if day is not None and not day.empty else 0
            n_buy = int((day["side"] == 1).sum()) if n and "side" in day.columns else 0
            shadow_summary.append({
                "strategy_id": sid,
                "status": eligibility(sid).status,
                "signals_day": n,
                "buy_day": n_buy,
                "path": "SHADOW",
            })

    return {
        "production_day": prod_day if prod_day is not None else pd.DataFrame(),
        "production_all": prod_all,
        "shadow": {k: v for k, v in shadow_map.items()},
        "shadow_day_summary": shadow_summary,
        "feature_meta": fmeta,
        "control_plane": control,
        "strategy_id": strategy_id,
        "path": "FEATURE_SSOT",
    }
