"""Structured signal/portfolio reporting — single source of truth for Telegram numbers."""
from src.python.reporting.finance import (
    SHARES_PER_LOT,
    shares_from_lots,
    lots_from_shares,
    position_value,
    exposure_pct,
    risk_amount,
    risk_pct,
    reward_risk_ratio,
    unrealized_pnl_long,
    realized_pnl_long,
)
from src.python.reporting.models import (
    SignalReport,
    PortfolioSnapshot,
    OpenPositionView,
    ExitReport,
    CycleReport,
)
from src.python.reporting.validation import (
    validate_position_math,
    validate_portfolio_math,
    validate_exit_report,
    validate_signal_report,
    validate_cycle_report,
    validate_telegram_payload,
    ValidationError,
)
from src.python.reporting.composer import (
    DeterministicComposer,
    compose_telegram_message,
)
from src.python.reporting.llm_boundary import (
    validate_llm_output,
    LLMMutationError,
    safe_compose,
)
from src.python.reporting.builder import (
    build_cycle_report,
    build_buy_signal,
    build_portfolio_snapshot,
    build_open_position,
    build_exit_from_trade,
)

__all__ = [
    "SHARES_PER_LOT",
    "shares_from_lots",
    "lots_from_shares",
    "position_value",
    "exposure_pct",
    "risk_amount",
    "risk_pct",
    "reward_risk_ratio",
    "unrealized_pnl_long",
    "realized_pnl_long",
    "SignalReport",
    "PortfolioSnapshot",
    "OpenPositionView",
    "ExitReport",
    "CycleReport",
    "validate_position_math",
    "validate_portfolio_math",
    "validate_exit_report",
    "validate_signal_report",
    "validate_cycle_report",
    "validate_telegram_payload",
    "ValidationError",
    "DeterministicComposer",
    "compose_telegram_message",
    "validate_llm_output",
    "LLMMutationError",
    "safe_compose",
    "build_cycle_report",
    "build_buy_signal",
    "build_portfolio_snapshot",
    "build_open_position",
    "build_exit_from_trade",
]
