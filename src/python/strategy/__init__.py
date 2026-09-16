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
from src.python.strategy.evidence import EvidencePackage, HardRejectCode
from src.python.strategy.evaluator import (
    EvaluatorConfig,
    StrategyEvaluator,
    evaluate_rule_sma20,
    sma20_signal_fn,
)

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
    "EvidencePackage",
    "HardRejectCode",
    "EvaluatorConfig",
    "StrategyEvaluator",
    "evaluate_rule_sma20",
    "sma20_signal_fn",
]
