"""Strategy registry — declare families; promotion status gates production use."""
from __future__ import annotations

from typing import Optional

from src.python.strategy.contracts import StrategyFamily, StrategySpec

STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    "rule_sma20": StrategySpec(
        strategy_id="rule_sma20",
        family=StrategyFamily.RULE_SMA,
        display="SMA20 trend filter (ops baseline)",
        description="Close above SMA20; ranking by distance. Current operational path.",
        required_features=("sma_dist_20",),
        compatible_regimes=(),
        default_weight=1.0,
        status="PROMOTED",  # only existing live path
    ),
    "trend_multi": StrategySpec(
        strategy_id="trend_multi",
        family=StrategyFamily.TREND,
        display="Multi-period trend following",
        description="SMA/EMA multi-period, slope, persistence, breakout distance.",
        required_features=("sma_dist_20", "sma_dist_50", "sma_slope_20", "trend_persist_20"),
        compatible_regimes=("bull", "bear"),
        default_weight=1.0,
        status="RESEARCH",
    ),
    "momentum_cs": StrategySpec(
        strategy_id="momentum_cs",
        family=StrategyFamily.MOMENTUM,
        display="Cross-sectional momentum",
        description="Return 5/10/20/60d + CS rank + acceleration.",
        required_features=("ret_5d", "ret_20d", "cs_mom_rank", "mom_accel_5"),
        compatible_regimes=(),
        default_weight=1.0,
        status="RESEARCH",
    ),
    "breakout_donchian": StrategySpec(
        strategy_id="breakout_donchian",
        family=StrategyFamily.BREAKOUT,
        display="Donchian / high-low breakout",
        description="20/50 high breakout with volume confirmation.",
        required_features=("breakout_high_20", "vol_z_20", "natr_14"),
        compatible_regimes=("bull",),
        default_weight=0.8,
        status="RESEARCH",
    ),
    "mean_reversion_z": StrategySpec(
        strategy_id="mean_reversion_z",
        family=StrategyFamily.MEAN_REVERSION,
        display="Mean reversion (z / SMA distance)",
        description="Only active in neutral/ranging regimes; z-score and SMA distance.",
        required_features=("sma_dist_20", "ret_std_20"),
        compatible_regimes=("neutral",),
        default_weight=0.7,
        status="RESEARCH",
    ),
    "volume_liquidity": StrategySpec(
        strategy_id="volume_liquidity",
        family=StrategyFamily.VOLUME_LIQUIDITY,
        display="Volume / liquidity alpha",
        description="Abnormal volume, turnover acceleration, volume-price confirm.",
        required_features=("vol_z_20", "vol_accel_5", "turnover_ma_ratio_20"),
        compatible_regimes=(),
        default_weight=0.6,
        status="RESEARCH",
    ),
    "relative_strength": StrategySpec(
        strategy_id="relative_strength",
        family=StrategyFamily.RELATIVE_STRENGTH,
        display="Relative strength vs IHSG / peers",
        description="Stock vs IHSG and cross-sectional RS ranking.",
        required_features=("rel_ret_5d_ihsg", "rel_mom_20_ihsg", "cs_rel_str_rank"),
        compatible_regimes=(),
        default_weight=1.0,
        status="RESEARCH",
    ),
    "vol_regime": StrategySpec(
        strategy_id="vol_regime",
        family=StrategyFamily.VOLATILITY_REGIME,
        display="Volatility / regime overlay",
        description="Adjusts exposure and eligibility by vol/trend/drawdown regime.",
        required_features=("regime_vol", "regime_trend", "regime_dd"),
        compatible_regimes=(),
        default_weight=0.5,
        status="RESEARCH",
    ),
}


def list_strategies(*, status: Optional[str] = None) -> list[StrategySpec]:
    specs = list(STRATEGY_REGISTRY.values())
    if status:
        specs = [s for s in specs if s.status == status]
    return sorted(specs, key=lambda s: (s.family.value, s.strategy_id))


def get_strategy(strategy_id: str) -> StrategySpec:
    if strategy_id not in STRATEGY_REGISTRY:
        raise KeyError(f"unknown_strategy:{strategy_id}")
    return STRATEGY_REGISTRY[strategy_id]


def promoted_ids() -> list[str]:
    return [s.strategy_id for s in STRATEGY_REGISTRY.values() if s.status == "PROMOTED"]
