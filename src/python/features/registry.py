"""Feature metadata registry — honest availability contracts."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    family: str
    tier: int
    required_columns: tuple[str, ...]
    lookback: int
    point_in_time_safe: bool = True
    normalization: str = "none"
    nan_policy: str = "propagate"
    cost_class: str = "low"
    definition: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _specs() -> list[FeatureSpec]:
    S = FeatureSpec
    out: list[FeatureSpec] = []
    for h in (1, 2, 3, 5, 10, 20, 60):
        out.append(S(f"ret_{h}d", "price_return", 0 if h <= 20 else 1, ("close",), h, definition=f"close.pct_change({h}) at T"))
        out.append(S(f"logret_{h}d", "price_return", 0 if h <= 5 else 1, ("close",), h, definition=f"log(close_T/close_T-{h})"))
    out += [
        S("ret_cum_5d", "price_return", 0, ("close",), 5, definition="(c/c.shift(5))-1"),
        S("ret_cum_20d", "price_return", 0, ("close",), 20, definition="(c/c.shift(20))-1"),
        S("overnight_gap", "price_return", 0, ("open", "close"), 1, definition="open_T/close_T-1 - 1"),
        S("intraday_range_pct", "price_return", 0, ("high", "low", "close"), 1, definition="(H-L)/C"),
        S("close_loc_in_range", "price_return", 0, ("high", "low", "close"), 1, definition="(C-L)/(H-L)"),
        S("dist_from_high_20", "price_return", 0, ("close", "high"), 20, definition="C/rolling_max(H,20)-1"),
        S("dist_from_low_20", "price_return", 0, ("close", "low"), 20, definition="C/rolling_min(L,20)-1"),
        S("rolling_dd_20", "price_return", 1, ("close",), 20, definition="C/rolling_max(C,20)-1"),
        S("rolling_dd_60", "price_return", 1, ("close",), 60, definition="C/rolling_max(C,60)-1"),
    ]
    for w in (5, 10, 20, 50, 100, 200):
        tier = 0 if w <= 50 else 1
        out.append(S(f"sma_dist_{w}", "trend_momentum", tier, ("close",), w, definition=f"C/SMA({w})-1"))
        out.append(S(f"ema_dist_{w}", "trend_momentum", 1 if w >= 50 else 0, ("close",), w, definition=f"C/EMA({w})-1", cost_class="medium" if w >= 100 else "low"))
        out.append(S(f"sma_slope_{w}", "trend_momentum", 1, ("close",), w + 1, definition=f"SMA({w}).pct_change(1)"))
    out += [
        S("mom_10_21", "trend_momentum", 0, ("close",), 21, definition="ret_10 - ret_21 proxy"),
        S("mom_accel_5", "trend_momentum", 1, ("close",), 10, definition="ret_5 - ret_5.shift(5)"),
        S("trend_persist_20", "trend_momentum", 1, ("close",), 20, definition="sign consistency of daily ret"),
        S("breakout_high_20", "trend_momentum", 0, ("close", "high"), 20, definition="C/rollmax(H,20)-1"),
        S("breakout_low_20", "trend_momentum", 0, ("close", "low"), 20, definition="C/rollmin(L,20)-1"),
    ]
    out += [
        S("atr_14", "volatility", 1, ("high", "low", "close"), 14, definition="ATR(14)", cost_class="medium"),
        S("natr_14", "volatility", 1, ("high", "low", "close"), 14, definition="ATR/C", cost_class="medium"),
        S("ret_std_10", "volatility", 0, ("close",), 10, definition="std(ret_1,10)"),
        S("ret_std_20", "volatility", 0, ("close",), 20, definition="std(ret_1,20)"),
        S("downside_vol_20", "volatility", 1, ("close",), 20, definition="std of negative ret"),
        S("upside_vol_20", "volatility", 1, ("close",), 20, definition="std of positive ret"),
        S("parkinson_20", "volatility", 1, ("high", "low"), 20, definition="Parkinson vol", cost_class="medium"),
        S("garman_klass_20", "volatility", 2, ("open", "high", "low", "close"), 20, definition="GK vol", cost_class="high"),
        S("rogers_satchell_20", "volatility", 2, ("open", "high", "low", "close"), 20, definition="RS vol", cost_class="high"),
        S("vol_ratio_10_40", "volatility", 1, ("close",), 40, definition="std10/std40"),
        S("vol_expand_20", "volatility", 1, ("close",), 40, definition="std20/std20.shift(20)"),
        S("max_range_20", "volatility", 1, ("high", "low"), 20, definition="max((H-L)/C,20)"),
    ]
    out += [
        S("volume_raw", "volume_liquidity", 0, ("volume",), 1, definition="volume as-is; NaN if missing"),
        S("log_volume", "volume_liquidity", 0, ("volume",), 1, definition="log1p(volume)", normalization="log"),
        S("vol_ma_ratio_20", "volume_liquidity", 0, ("volume",), 20, definition="V/mean(V,20)"),
        S("vol_z_20", "volume_liquidity", 0, ("volume",), 20, definition="zscore volume"),
        S("vol_accel_5", "volume_liquidity", 1, ("volume",), 10, definition="ratio change"),
        S("vol_trend_20", "volume_liquidity", 1, ("volume",), 20, definition="V/V.shift(20)-1"),
        S("abnormal_vol_20", "volume_liquidity", 1, ("volume",), 20, definition="1 if z>2"),
        S("turnover", "volume_liquidity", 0, ("close", "volume"), 1, definition="C*V"),
        S("turnover_ma_ratio_20", "volume_liquidity", 1, ("close", "volume"), 20, definition="TO/mean(TO,20)"),
        S("zero_volume_flag", "volume_liquidity", 0, ("volume",), 1, definition="1 if volume==0"),
        S("missing_volume_flag", "volume_liquidity", 0, ("volume",), 1, definition="1 if volume is NaN"),
        S("volume_quality", "volume_liquidity", 0, ("volume",), 1, definition="1 valid, 0 missing/invalid"),
    ]
    for name, fam, tier, lb, defn in [
        ("rel_ret_1d_ihsg", "relative_strength", 1, 1, "ret_stock - ret_ihsg"),
        ("rel_ret_5d_ihsg", "relative_strength", 1, 5, "ret5_stock - ret5_ihsg"),
        ("rel_mom_20_ihsg", "relative_strength", 1, 20, "cum20 stock - cum20 ihsg"),
        ("rel_vol_20_ihsg", "relative_strength", 1, 20, "vol_stock/vol_ihsg"),
        ("ihsg_ret_1d", "market_context", 0, 1, "IHSG ret 1d"),
        ("ihsg_ret_5d", "market_context", 0, 5, "IHSG ret 5d"),
        ("ihsg_mom_20", "market_context", 1, 20, "IHSG cum 20"),
        ("ihsg_vol_20", "market_context", 1, 20, "IHSG ret std 20"),
        ("ihsg_dd_60", "market_context", 1, 60, "IHSG drawdown 60"),
        ("ihsg_trend_regime", "market_context", 1, 50, "sign of SMA50 slope"),
        ("mkt_vol_regime", "market_context", 1, 40, "vol ratio regime code"),
        ("mkt_stress", "market_context", 1, 20, "stress score"),
        ("cs_ret_rank", "cross_sectional", 1, 1, "rank of ret_1d at T"),
        ("cs_mom_rank", "cross_sectional", 1, 20, "rank of ret_20d at T"),
        ("cs_vol_rank", "cross_sectional", 1, 20, "rank of vol at T"),
        ("cs_volume_rank", "cross_sectional", 1, 1, "rank of volume at T"),
        ("cs_rel_str_rank", "cross_sectional", 1, 5, "rank of rel ret"),
        ("cs_dist_high_rank", "cross_sectional", 1, 20, "rank of dist_from_high_20"),
        ("regime_trend", "regime", 1, 50, "bull/bear/neutral code"),
        ("regime_vol", "regime", 1, 40, "low/med/high vol code"),
        ("regime_vol_expand", "regime", 1, 40, "expand/contract code"),
        ("regime_dd", "regime", 1, 60, "drawdown regime"),
        ("regime_momentum", "regime", 1, 20, "mom regime"),
        ("regime_liquidity", "regime", 1, 20, "liquidity regime"),
        ("dq_missing_ohlc", "data_quality", 0, 1, "flag"),
        ("dq_missing_volume", "data_quality", 0, 1, "flag"),
        ("dq_zero_volume", "data_quality", 0, 1, "flag"),
        ("dq_abnormal_ohlc", "data_quality", 0, 1, "H<L or C out of range"),
        ("dq_insufficient_hist", "data_quality", 0, 1, "1 if bar index < min lookback"),
        ("dq_stale_gap", "data_quality", 1, 5, "calendar gap days"),
    ]:
        cols = ("close",) if "volume" not in name else ("close", "volume")
        if "ohlc" in name:
            cols = ("open", "high", "low", "close")
        out.append(S(name, fam, tier, cols, lb, definition=defn, cost_class="medium" if tier >= 1 else "low"))
    return out


FEATURE_REGISTRY: dict[str, FeatureSpec] = {s.name: s for s in _specs()}


def registry_summary() -> dict[str, Any]:
    by_fam: dict[str, int] = {}
    by_tier = {0: 0, 1: 0, 2: 0}
    for s in FEATURE_REGISTRY.values():
        by_fam[s.family] = by_fam.get(s.family, 0) + 1
        by_tier[s.tier] = by_tier.get(s.tier, 0) + 1
    return {"n_features": len(FEATURE_REGISTRY), "by_family": by_fam, "by_tier": by_tier, "names": sorted(FEATURE_REGISTRY.keys())}
