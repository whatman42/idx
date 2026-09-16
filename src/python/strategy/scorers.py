"""Strategy scorers — consume FeatureSnapshot only (Phase 2A.1 / 2B.1).

No OHLCV recomputation. No rolling/shift in scorers.
"""
from __future__ import annotations

import math
from typing import Any, Sequence

import pandas as pd

from src.python.features.registry import FEATURE_REGISTRY
from src.python.strategy.contracts import AlphaScore
from src.python.strategy.feature_snapshot import (
    FeatureSnapshot,
    assert_required_features_registered,
    is_forbidden_feature_name,
)
from src.python.strategy.registry import get_strategy


def _finite(x: float) -> bool:
    return x == x and math.isfinite(x)


def _tanh(x: float) -> float:
    try:
        return math.tanh(float(x))
    except (TypeError, ValueError):
        return 0.0


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class RuleSMA20Scorer:
    """Control group: BUY when sma_dist_20 > 0 (from Feature Engine, not recomputed)."""

    strategy_id = "rule_sma20"
    required_features: Sequence[str] = ("sma_dist_20",)

    def __init__(self) -> None:
        assert_required_features_registered(self.required_features)

    def score_row(self, snap: FeatureSnapshot) -> dict[str, Any]:
        snap.require(self.required_features)
        dist = snap.get("sma_dist_20")
        if not _finite(dist):
            return {
                "side": 0,
                "confidence": 0.0,
                "score": 0.0,
                "symbol": snap.symbol,
                "timestamp": snap.timestamp,
                "strategy_id": self.strategy_id,
                "direction": 0,
                "regime_compatible": True,
                "reason": "sma_dist_20_nan",
            }
        side = 1 if dist > 0.0 else 0
        conf = min(0.99, 0.5 + abs(dist) * 5.0)
        return {
            "side": side,
            "confidence": float(conf),
            "score": float(dist),
            "symbol": snap.symbol,
            "timestamp": snap.timestamp,
            "strategy_id": self.strategy_id,
            "direction": 1 if side else 0,
            "regime_compatible": True,
            "reason": "sma_dist_20_gt_0" if side else "sma_dist_20_le_0",
        }

    def score_frame(self, feat_df: pd.DataFrame) -> pd.DataFrame:
        if feat_df is None or feat_df.empty:
            return pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "score"])
        if "sma_dist_20" not in feat_df.columns:
            raise KeyError("score_frame requires sma_dist_20 from Feature Engine")
        for c in feat_df.columns:
            if is_forbidden_feature_name(c):
                raise ValueError(f"forbidden label-like column in scorer frame: {c}")
        dist = pd.to_numeric(feat_df["sma_dist_20"], errors="coerce")
        side = (dist > 0.0).astype(int)
        side = side.where(dist.notna(), 0)
        conf = (0.5 + dist.abs() * 5.0).clip(upper=0.99).fillna(0.0)
        return pd.DataFrame({
            "timestamp": pd.to_datetime(feat_df["timestamp"]),
            "symbol": feat_df["symbol"].astype(str),
            "side": side.astype(int),
            "confidence": conf.astype(float),
            "score": dist.fillna(0.0).astype(float),
        })


class TrendMultiScorer:
    """Multi-period trend alpha — RESEARCH / SHADOW only.

    Input: FeatureSnapshot only (Feature Engine SSOT). No OHLCV access.

    Score range: [-1, +1]

    Formula (deterministic):
      core = 0.30*tanh(sma_dist_20*10) + 0.20*tanh(sma_dist_50*8)
           + 0.10*tanh(ema_dist_20*10) [if finite]
           + 0.15*tanh(sma_slope_20*50)
      mom  = 0.15*tanh(mom_10_21*5)
      pers = 0.10*clip(trend_persist_20, -1, 1)
      brk  = 0.10*tanh(breakout_high_20*10)
      raw  = core + mom + pers + brk
      if rel_mom_20_ihsg finite: raw += 0.05*tanh(rel_mom_20_ihsg*5)
      if ret_std_20 finite and > 0.04:
          raw -= 0.10 * clip((ret_std_20-0.04)/0.04, 0, 1)
      score = clip(raw, -1, 1)

    Regime gating (registry compatible_regimes: bull|bear):
      regime_trend > 0.25 → bull; < -0.25 → bear; else neutral
      neutral → regime_compatible=False, side=0 (NO_SIGNAL for evaluator path)
    """

    strategy_id = "trend_multi"
    required_features: Sequence[str] = (
        "sma_dist_20",
        "sma_dist_50",
        "sma_slope_20",
        "trend_persist_20",
        "mom_10_21",
        "breakout_high_20",
    )
    optional_features: Sequence[str] = (
        "ema_dist_20",
        "rel_mom_20_ihsg",
        "ret_std_20",
        "regime_trend",
        "regime_vol",
    )
    score_min: float = -1.0
    score_max: float = 1.0

    def __init__(self) -> None:
        assert_required_features_registered(self.required_features)
        for f in self.optional_features:
            if f in FEATURE_REGISTRY:
                assert_required_features_registered([f])
        spec = get_strategy(self.strategy_id)
        if spec.status != "RESEARCH":
            raise RuntimeError("trend_multi must remain RESEARCH until PromotionGate PASS")

    def _regime_label(self, snap: FeatureSnapshot) -> str:
        code = snap.get("regime_trend", 0.0)
        if not _finite(code):
            return "neutral"
        if code > 0.25:
            return "bull"
        if code < -0.25:
            return "bear"
        return "neutral"

    def _compute_raw(self, snap: FeatureSnapshot) -> tuple[float, list[str]]:
        reasons: list[str] = []
        d20 = snap.get("sma_dist_20")
        d50 = snap.get("sma_dist_50")
        slope = snap.get("sma_slope_20")
        persist = snap.get("trend_persist_20")
        mom = snap.get("mom_10_21")
        brk = snap.get("breakout_high_20")

        for name, val in (
            ("sma_dist_20", d20),
            ("sma_dist_50", d50),
            ("sma_slope_20", slope),
            ("trend_persist_20", persist),
            ("mom_10_21", mom),
            ("breakout_high_20", brk),
        ):
            if not _finite(val):
                raise ValueError(f"trend_multi required feature non-finite: {name}")

        core = (
            0.30 * _tanh(d20 * 10.0)
            + 0.20 * _tanh(d50 * 8.0)
            + 0.15 * _tanh(slope * 50.0)
        )
        ema = snap.get("ema_dist_20")
        if _finite(ema):
            core += 0.10 * _tanh(ema * 10.0)
            reasons.append("ema_confirm")

        mom_t = 0.15 * _tanh(mom * 5.0)
        pers_t = 0.10 * _clip(persist, -1.0, 1.0)
        brk_t = 0.10 * _tanh(brk * 10.0)
        raw = core + mom_t + pers_t + brk_t

        rs = snap.get("rel_mom_20_ihsg")
        if _finite(rs):
            raw += 0.05 * _tanh(rs * 5.0)
            reasons.append("rs_context")

        vol = snap.get("ret_std_20")
        if _finite(vol) and vol > 0.04:
            pen = 0.10 * _clip((vol - 0.04) / 0.04, 0.0, 1.0)
            raw -= pen
            reasons.append(f"vol_penalty={pen:.3f}")

        score = _clip(raw, self.score_min, self.score_max)
        if score > 0.15:
            reasons.append("trend_long_bias")
        elif score < -0.15:
            reasons.append("trend_short_bias")
        else:
            reasons.append("trend_weak")
        return float(score), reasons

    def score_row(self, snap: FeatureSnapshot) -> dict[str, Any]:
        snap.require(self.required_features)
        score, reasons = self._compute_raw(snap)
        regime = self._regime_label(snap)
        compatible = regime in ("bull", "bear")
        if not compatible:
            reasons = list(reasons) + [f"regime_gate={regime}"]
            return {
                "side": 0,
                "confidence": 0.0,
                "score": float(score),
                "symbol": snap.symbol,
                "timestamp": snap.timestamp,
                "strategy_id": self.strategy_id,
                "direction": 0,
                "regime_compatible": False,
                "regime": regime,
                "reason": ";".join(reasons),
                "reasons": reasons,
            }

        direction = 1 if score > 0.0 else (-1 if score < 0.0 else 0)
        side = 1 if score > 0.10 else 0
        conf = min(0.99, abs(score))
        reasons = list(reasons) + [f"regime={regime}"]
        return {
            "side": int(side),
            "confidence": float(conf),
            "score": float(score),
            "symbol": snap.symbol,
            "timestamp": snap.timestamp,
            "strategy_id": self.strategy_id,
            "direction": int(direction),
            "regime_compatible": True,
            "regime": regime,
            "reason": ";".join(reasons),
            "reasons": reasons,
        }

    def to_alpha_score(self, snap: FeatureSnapshot) -> AlphaScore:
        r = self.score_row(snap)
        return AlphaScore(
            strategy_id=self.strategy_id,
            family="TREND",
            symbol=str(r["symbol"]),
            score=float(r["score"]),
            direction=int(r["direction"]),
            confidence=float(r["confidence"]),
            reasons=list(r.get("reasons") or [r.get("reason", "")]),
            regime_compatible=bool(r.get("regime_compatible", True)),
            meta={"regime": r.get("regime"), "side": r.get("side")},
        )

    def score_frame(self, feat_df: pd.DataFrame) -> pd.DataFrame:
        if feat_df is None or feat_df.empty:
            return pd.DataFrame(
                columns=["timestamp", "symbol", "side", "confidence", "score", "direction", "regime_compatible"]
            )
        for c in feat_df.columns:
            if is_forbidden_feature_name(c):
                raise ValueError(f"forbidden label-like column in scorer frame: {c}")
        missing = [f for f in self.required_features if f not in feat_df.columns]
        if missing:
            raise KeyError(f"trend_multi score_frame missing required features: {missing}")

        rows: list[dict[str, Any]] = []
        for _, row in feat_df.iterrows():
            feats: dict[str, float] = {}
            for c in list(self.required_features) + list(self.optional_features):
                if c in row.index and not is_forbidden_feature_name(c):
                    try:
                        feats[c] = float(row[c]) if pd.notna(row[c]) else float("nan")
                    except (TypeError, ValueError):
                        feats[c] = float("nan")
            snap = FeatureSnapshot(
                timestamp=str(row["timestamp"]),
                symbol=str(row["symbol"]),
                features=feats,
            )
            try:
                r = self.score_row(snap)
            except ValueError:
                r = {
                    "side": 0,
                    "confidence": 0.0,
                    "score": 0.0,
                    "direction": 0,
                    "regime_compatible": False,
                }
            rows.append({
                "timestamp": row["timestamp"],
                "symbol": str(row["symbol"]),
                "side": int(r["side"]),
                "confidence": float(r["confidence"]),
                "score": float(r["score"]),
                "direction": int(r.get("direction", 0)),
                "regime_compatible": bool(r.get("regime_compatible", True)),
            })
        return pd.DataFrame(rows)


def get_scorer(strategy_id: str):
    if strategy_id == "rule_sma20":
        return RuleSMA20Scorer()
    if strategy_id == "trend_multi":
        return TrendMultiScorer()
    raise KeyError(f"scorer_not_implemented:{strategy_id}")
