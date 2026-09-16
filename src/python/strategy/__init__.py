"""Multi-strategy alpha engine — contracts first, promotion before production."""
from src.python.strategy.contracts import (
    AlphaScore,
    EnsembleInput,
    OrderIntent,
    RegimeState,
    SignalDecision,
    StrategySpec,
)
from src.python.strategy.ensemble import EnsembleGovernor
from src.python.strategy.regime import RegimeEngine
from src.python.strategy.registry import STRATEGY_REGISTRY, list_strategies
from src.python.strategy.promotion_gate import PromotionGate, PromotionStage

__all__ = [
    "AlphaScore",
    "EnsembleInput",
    "OrderIntent",
    "RegimeState",
    "SignalDecision",
    "StrategySpec",
    "EnsembleGovernor",
    "RegimeEngine",
    "STRATEGY_REGISTRY",
    "list_strategies",
    "PromotionGate",
    "PromotionStage",
]
