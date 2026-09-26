"""Research plane vs Production plane — locked architectural contract.

RESEARCH PLANE
  OHLCV + candidate strategy
        → StrategyEvaluator
            full-sample, costs, TP/SL/hold, signal_T→open_T+1,
            no-look-ahead, walk-forward, DQ, hard-rejects
        → EvidencePackage
        → PromotionGate (PASS eligible / FAIL rejected)
        → StrategyLifecycle / authority

PRODUCTION PLANE
  signal_bot → ExecutionGate → Paper Portfolio → Ledger

FORBIDDEN edges (must never exist):
  Evaluator → PaperPortfolio
  Evaluator → Ledger
  Evaluator → Telegram
  Evaluator → champion mutation
  Evaluator → BUY/SELL authority

ONLY valid research promotion path:
  Evaluator → EvidencePackage → PromotionGate

Timing invariant:
  signal at T → decision fixed at T → execution simulated at Open(T+1)
  (no Close(T+1) or future bars in decision at T)

LIVE_EXECUTION = FALSE on both planes for paper system.
"""
from __future__ import annotations

from typing import Any, FrozenSet

RESEARCH_PLANE_MODULES: FrozenSet[str] = frozenset({
    "src.python.strategy.evaluator",
    "src.python.strategy.evidence",
    "src.python.strategy.evidence_schema",
    "src.python.strategy.evidence_freeze",
    "src.python.strategy.promotion_gate",
    "src.python.strategy.promotion_invariants",
    "src.python.strategy.feature_snapshot",
    "src.python.strategy.feature_pipeline",
    "src.python.strategy.scorers",
    "src.python.research",
})

PRODUCTION_FORBIDDEN_IMPORTS: FrozenSet[str] = frozenset({
    "src.python.ops.paper_portfolio",
    "src.python.ops.signal_bot",
    "src.python.ops.notify_state",
    "src.python.notify",
    "src.python.ops.telegram_format",
})

PRODUCTION_FORBIDDEN_SYMBOLS: FrozenSet[str] = frozenset({
    "PaperPortfolioStore",
    "apply_long_entry",
    "new_session",
    "send_telegram",
    "notify_telegram",
    "promote_champion",
    "set_champion",
})

VALID_EVALUATOR_OUTPUT = "EvidencePackage"
VALID_PROMOTION_PATH = ("EvidencePackage", "PromotionGate", "StrategyLifecycle")

TIMING_CONTRACT = "signal_T_execute_open_Tplus1"


def describe_plane_contract() -> dict[str, Any]:
    return {
        "version": "plane_contract_v1",
        "live_execution": False,
        "broker_execution": False,
        "research": {
            "entry": "StrategyEvaluator.evaluate",
            "output": VALID_EVALUATOR_OUTPUT,
            "path": list(VALID_PROMOTION_PATH),
            "timing": TIMING_CONTRACT,
            "authority": False,
            "writes_ledger": False,
            "writes_paper": False,
            "sends_telegram": False,
            "mutates_champion": False,
        },
        "production": {
            "entry": "signal_bot.run",
            "path": [
                "signal_bot",
                "RiskGate",
                "IDX enrichment (optional facts)",
                "ExecutionGate",
                "PaperPortfolio",
                "Ledger",
            ],
            "requires_promoted_authority": True,
        },
        "forbidden_edges": [
            "Evaluator→PaperPortfolio",
            "Evaluator→Ledger",
            "Evaluator→Telegram",
            "Evaluator→champion",
            "Evaluator→BUY/SELL authority",
        ],
        "roles": {
            "StrategyEvaluator": "evidence generation",
            "EvidencePackage": "structured versioned evidence",
            "PromotionGate": "promotion control",
            "signal_bot": "daily operations",
            "ExecutionGate": "execution eligibility",
            "PaperPortfolio": "simulated execution",
            "Ledger": "P&L SSOT",
        },
    }


def assert_evaluator_module_isolation(evaluator_source: str) -> None:
    """Static check: evaluator source text must not reference production writers."""
    for sym in PRODUCTION_FORBIDDEN_SYMBOLS:
        if sym not in evaluator_source:
            continue
        for line in evaluator_source.splitlines():
            if sym not in line:
                continue
            s = line.strip()
            if s.startswith("#") or s.startswith('"""') or s.startswith("'''"):
                continue
            if "signal_bot unchanged" in line or "Live signal_bot" in line:
                continue
            if f"import {sym}" in line or f"{sym}(" in line or (
                line.strip().startswith("from ") and sym in line
            ):
                raise AssertionError(f"Evaluator must not use production symbol: {sym}")


def assert_no_forbidden_imports_in_module(mod) -> list[str]:
    hits: list[str] = []
    for key, val in vars(mod).items():
        modname = getattr(val, "__module__", "") or ""
        for forbidden in PRODUCTION_FORBIDDEN_IMPORTS:
            if modname.startswith(forbidden) or forbidden in modname:
                hits.append(f"{key}:{modname}")
    return hits
