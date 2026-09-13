"""Point-in-time feature engine. Feature(T) uses only data <= T."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import numpy as np
import pandas as pd

from src.python.features.registry import FEATURE_REGISTRY, registry_summary
from src.python.features.tiers import FeatureTier, tier_feature_names
from src.python.features.version import FEATURE_SET_VERSION

IHSG_SYMBOLS = ("IHSG", "^JKSE", "JKSE", "COMPOSITE")


@dataclass
class FeatureBuildResult:
    df: pd.DataFrame
    feature_set_version: str
    max_tier: int
    feature_names: list[str]
    n_rows: int
    n_symbols: int
    meta: dict[str, Any] = field(default_factory=dict)


def _ensure_cols(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["timestamp"] = pd.to_datetime(d["timestamp"])
    for c in ("open", "high", "low", "close"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    if "volume" in d.columns:
        d["volume"] = pd.to_numeric(d["volume"], errors="coerce")
    d = d.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    return d


def _extract_benchmark(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    syms = set(df["symbol"].astype(str).unique())
    for s in IHSG_SYMBOLS:
        if s in syms:
            b = df[df["symbol"].astype(str) == s][["timestamp", "open", "high", "low", "close", "volume"]].copy()
            return b.sort_values("timestamp")
    return None


def _symbol_features(g: pd.DataFrame, bench: Optional[pd.DataFrame]) -> pd.DataFrame:
    g = g.sort_values("timestamp").reset_index(drop=True)
    n = len(g)
    c = g["close"]
    o = g["open"] if "open" in g.columns else c
    h = g["high"] if "high" in g.columns else c
    low = g["low"] if "low" in g.columns else c
    v = g["volume"] if "volume" in g.columns else pd.Series(np.nan, index=g.index)

    r1 = c.pct_change(1)
    out = pd.DataFrame({"timestamp": g["timestamp"].values, "symbol": g["symbol"].astype(str).values})

    for k in (1, 2, 3, 5, 10, 20, 60):
        out[f"ret_{k}d"] = c.pct_change(k)
        lr = np.log(c / c.shift(k))
        out[f"logret_{k}d"] = lr.replace([np.inf, -np.inf], np.nan)
    out["ret_cum_5d"] = c / c.shift(5) - 1.0
    out["ret_cum_20d"] = c / c.shift(20) - 1.0
    out["overnight_gap"] = o / c.shift(1) - 1.0
    rng = (h - low)
    out["intraday_range_pct"] = rng / c.replace(0, np.nan)
    out["close_loc_in_range"] = (c - low) / rng.replace(0, np.nan)
    roll_max_h20 = h.rolling(20, min_periods=5).max()
    roll_min_l20 = low.rolling(20, min_periods=5).min()
    out["dist_from_high_20"] = c / roll_max_h20 - 1.0
    out["dist_from_low_20"] = c / roll_min_l20 - 1.0
    out["rolling_dd_20"] = c / c.rolling(20, min_periods=5).max() - 1.0
    out["rolling_dd_60"] = c / c.rolling(60, min_periods=10).max() - 1.0

    for w in (5, 10, 20, 50, 100, 200):
        sma = c.rolling(w, min_periods=max(3, w // 5)).mean()
        ema = c.ewm(span=w, adjust=False, min_periods=max(3, w // 5)).mean()
        out[f"sma_dist_{w}"] = c / sma - 1.0
        out[f"ema_dist_{w}"] = c / ema - 1.0
        out[f"sma_slope_{w}"] = sma.pct_change(1)
    out["mom_10_21"] = c.pct_change(10) - c.pct_change(21)
    out["mom_accel_5"] = c.pct_change(5) - c.pct_change(5).shift(5)
    sign = np.sign(r1.fillna(0))
    out["trend_persist_20"] = sign.rolling(20, min_periods=5).mean()
    out["breakout_high_20"] = out["dist_from_high_20"]
    out["breakout_low_20"] = out["dist_from_low_20"]

    tr = pd.concat([(h - low), (h - c.shift(1)).abs(), (low - c.shift(1)).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=5).mean()
    out["atr_14"] = atr
    out["natr_14"] = atr / c.replace(0, np.nan)
    out["ret_std_10"] = r1.rolling(10, min_periods=5).std()
    out["ret_std_20"] = r1.rolling(20, min_periods=5).std()
    neg = r1.where(r1 < 0)
    pos = r1.where(r1 > 0)
    out["downside_vol_20"] = neg.rolling(20, min_periods=5).std()
    out["upside_vol_20"] = pos.rolling(20, min_periods=5).std()
    hl = np.log(h / low.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
    out["parkinson_20"] = np.sqrt((hl ** 2).rolling(20, min_periods=5).mean() / (4 * np.log(2)))
    if "open" in g.columns:
        log_hl = np.log(h / low.replace(0, np.nan)) ** 2
        log_co = np.log(c / o.replace(0, np.nan)) ** 2
        gk = 0.5 * log_hl - (2 * np.log(2) - 1) * log_co
        out["garman_klass_20"] = np.sqrt(gk.rolling(20, min_periods=5).mean().clip(lower=0))
        rs = np.log(h / c.replace(0, np.nan)) * np.log(h / o.replace(0, np.nan)) + np.log(
            low / c.replace(0, np.nan)
        ) * np.log(low / o.replace(0, np.nan))
        out["rogers_satchell_20"] = np.sqrt(rs.rolling(20, min_periods=5).mean().clip(lower=0))
    else:
        out["garman_klass_20"] = np.nan
        out["rogers_satchell_20"] = np.nan
    std10 = out["ret_std_10"]
    std40 = r1.rolling(40, min_periods=10).std()
    out["vol_ratio_10_40"] = std10 / std40.replace(0, np.nan)
    std20 = out["ret_std_20"]
    out["vol_expand_20"] = std20 / std20.shift(20).replace(0, np.nan)
    out["max_range_20"] = (rng / c.replace(0, np.nan)).rolling(20, min_periods=5).max()

    missing_v = v.isna()
    zero_v = (v == 0) & ~missing_v
    out["volume_raw"] = v
    out["log_volume"] = np.log1p(v.clip(lower=0)).where(~missing_v, np.nan)
    v_ma = v.rolling(20, min_periods=5).mean()
    v_std = v.rolling(20, min_periods=5).std()
    out["vol_ma_ratio_20"] = v / v_ma.replace(0, np.nan)
    out["vol_z_20"] = (v - v_ma) / v_std.replace(0, np.nan)
    out["vol_accel_5"] = out["vol_ma_ratio_20"] / out["vol_ma_ratio_20"].shift(5) - 1.0
    out["vol_trend_20"] = v / v.shift(20) - 1.0
    out["abnormal_vol_20"] = (out["vol_z_20"] > 2).astype(float)
    to = c * v
    out["turnover"] = to
    out["turnover_ma_ratio_20"] = to / to.rolling(20, min_periods=5).mean().replace(0, np.nan)
    out["zero_volume_flag"] = zero_v.astype(float)
    out["missing_volume_flag"] = missing_v.astype(float)
    out["volume_quality"] = (~missing_v & ~zero_v).astype(float)

    miss_ohlc = c.isna() | h.isna() | low.isna() | o.isna()
    abnormal = (h < low) | (c > h) | (c < low)
    out["dq_missing_ohlc"] = miss_ohlc.astype(float)
    out["dq_missing_volume"] = missing_v.astype(float)
    out["dq_zero_volume"] = zero_v.astype(float)
    out["dq_abnormal_ohlc"] = abnormal.astype(float)
    out["dq_insufficient_hist"] = (np.arange(n) < 20).astype(float)
    ts = pd.to_datetime(g["timestamp"])
    gap = ts.diff().dt.days.fillna(0)
    out["dq_stale_gap"] = gap.clip(lower=0)

    if bench is not None and not bench.empty:
        b = bench.sort_values("timestamp").copy()
        bc = b["close"]
        b["ihsg_ret_1d"] = bc.pct_change(1)
        b["ihsg_ret_5d"] = bc.pct_change(5)
        b["ihsg_mom_20"] = bc / bc.shift(20) - 1.0
        b["ihsg_vol_20"] = b["ihsg_ret_1d"].rolling(20, min_periods=5).std()
        b["ihsg_dd_60"] = bc / bc.rolling(60, min_periods=10).max() - 1.0
        sma50 = bc.rolling(50, min_periods=10).mean()
        b["ihsg_trend_regime"] = np.sign(sma50.pct_change(5)).fillna(0)
        vol_r = b["ihsg_vol_20"] / b["ihsg_vol_20"].rolling(40, min_periods=10).mean().replace(0, np.nan)
        b["mkt_vol_regime"] = pd.cut(vol_r, bins=[-np.inf, 0.8, 1.2, np.inf], labels=[0, 1, 2]).astype(float)
        b["mkt_stress"] = (-b["ihsg_dd_60"].clip(upper=0) * 5 + vol_r.fillna(1)).clip(0, 10)
        b_merge = b[["timestamp", "ihsg_ret_1d", "ihsg_ret_5d", "ihsg_mom_20", "ihsg_vol_20", "ihsg_dd_60", "ihsg_trend_regime", "mkt_vol_regime", "mkt_stress"]]
        out = pd.merge_asof(out.sort_values("timestamp"), b_merge.sort_values("timestamp"), on="timestamp", direction="backward")
        out["rel_ret_1d_ihsg"] = out["ret_1d"] - out["ihsg_ret_1d"]
        out["rel_ret_5d_ihsg"] = out["ret_5d"] - out["ihsg_ret_5d"]
        out["rel_mom_20_ihsg"] = out["ret_cum_20d"] - out["ihsg_mom_20"]
        out["rel_vol_20_ihsg"] = out["ret_std_20"] / out["ihsg_vol_20"].replace(0, np.nan)
    else:
        for col in ("ihsg_ret_1d", "ihsg_ret_5d", "ihsg_mom_20", "ihsg_vol_20", "ihsg_dd_60", "ihsg_trend_regime", "mkt_vol_regime", "mkt_stress", "rel_ret_1d_ihsg", "rel_ret_5d_ihsg", "rel_mom_20_ihsg", "rel_vol_20_ihsg"):
            out[col] = np.nan

    out["regime_trend"] = np.sign(out["sma_slope_50"].fillna(0))
    vr = out["vol_ratio_10_40"]
    out["regime_vol"] = pd.cut(vr, bins=[-np.inf, 0.8, 1.2, np.inf], labels=[0, 1, 2]).astype(float)
    out["regime_vol_expand"] = np.sign(out["vol_expand_20"].fillna(0) - 1.0)
    out["regime_dd"] = pd.cut(out["rolling_dd_60"], bins=[-np.inf, -0.2, -0.05, np.inf], labels=[2, 1, 0]).astype(float)
    out["regime_momentum"] = np.sign(out["ret_cum_20d"].fillna(0))
    out["regime_liquidity"] = pd.cut(out["vol_ma_ratio_20"], bins=[-np.inf, 0.5, 1.5, np.inf], labels=[0, 1, 2]).astype(float)
    out["y_next_up"] = (c.shift(-1) / c - 1.0 > 0).astype(float)
    return out


def _cross_section_ranks(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    d = df.copy()
    rank_map = {
        "cs_ret_rank": "ret_1d",
        "cs_mom_rank": "ret_cum_20d",
        "cs_vol_rank": "ret_std_20",
        "cs_volume_rank": "volume_raw",
        "cs_rel_str_rank": "rel_ret_5d_ihsg",
        "cs_dist_high_rank": "dist_from_high_20",
    }
    for dest, src in rank_map.items():
        if src not in d.columns:
            d[dest] = np.nan
            continue
        d[dest] = d.groupby("timestamp", sort=False)[src].rank(method="average", pct=True)
    return d


def build_features(
    bars: pd.DataFrame,
    *,
    max_tier: int | FeatureTier = FeatureTier.TIER1_STANDARD,
    include_benchmark_symbol: bool = True,
    feature_names: Optional[Sequence[str]] = None,
) -> FeatureBuildResult:
    if bars is None or bars.empty:
        return FeatureBuildResult(df=pd.DataFrame(), feature_set_version=FEATURE_SET_VERSION, max_tier=int(max_tier), feature_names=[], n_rows=0, n_symbols=0, meta={"status": "EMPTY"})
    df = _ensure_cols(bars)
    bench = _extract_benchmark(df) if include_benchmark_symbol else None
    stock_df = df
    if bench is not None:
        bench_syms = set(IHSG_SYMBOLS) & set(df["symbol"].astype(str).unique())
        stock_df = df[~df["symbol"].astype(str).isin(bench_syms)]
    parts = []
    for _, g in stock_df.groupby("symbol", sort=False):
        parts.append(_symbol_features(g, bench))
    if not parts:
        for _, g in df.groupby("symbol", sort=False):
            parts.append(_symbol_features(g, None))
    feat = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    feat = _cross_section_ranks(feat)
    feat = feat.replace([np.inf, -np.inf], np.nan)
    mt = int(max_tier)
    allowed = set(tier_feature_names(mt))
    if feature_names is not None:
        allowed = allowed.intersection(set(feature_names))
    id_cols = ["timestamp", "symbol"]
    cols = id_cols + [c for c in feat.columns if c in allowed]
    if "y_next_up" in feat.columns:
        cols = cols + ["y_next_up"]
    out_df = feat[cols].copy()
    return FeatureBuildResult(
        df=out_df,
        feature_set_version=FEATURE_SET_VERSION,
        max_tier=mt,
        feature_names=[c for c in cols if c not in id_cols and c != "y_next_up"],
        n_rows=len(out_df),
        n_symbols=int(out_df["symbol"].nunique()) if len(out_df) else 0,
        meta={"registry": registry_summary(), "benchmark_available": bench is not None, "feature_set_version": FEATURE_SET_VERSION},
    )
