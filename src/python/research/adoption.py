"""Architecture adoption decisions — ADOPT / ADAPT / REFERENCE / REJECT.

Derived from external benchmarks (Qlib, RD-Agent, FinRL-X, TradingAgents,
vectorbt, skfolio, LEAN, Nautilus, Freqtrade, …) mapped onto IDX constraints:

  GitHub Actions Free = cheap deterministic control plane
  Colab              = expensive research compute
  LLM                = reasoning / hypothesis only (never SSOT)
  PromotionGate      = mandatory evidence barrier
  Champion           = never auto-mutated
  Paper-only         = no live broker execution
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AdoptionDecision(str, Enum):
    ADOPT = "ADOPT"
    ADAPT = "ADAPT"
    REFERENCE = "REFERENCE_ONLY"
    REJECT = "REJECT"


@dataclass(frozen=True)
class AdoptionRow:
    source: str
    concept: str
    idx_target: str
    decision: AdoptionDecision
    rationale: str
    actions_cost: str
    leakage_risk: str
    test_requirement: str


ADOPTION_MATRIX: tuple[AdoptionRow, ...] = (
    AdoptionRow(
        "Qlib", "research workflow / alpha eval / drift",
        "research.factory + learning.drift + strategy.evaluator",
        AdoptionDecision.ADAPT,
        "Adopt workflow concepts; do not vendor Qlib runtime",
        "LOW", "MED", "WFA + PIT tests",
    ),
    AdoptionRow(
        "RD-Agent", "hypothesis → experiment → evaluate → iterate",
        "research.factory + learning.hypothesis + learning.experiment",
        AdoptionDecision.ADAPT,
        "Core of autonomous research factory; never auto-promote",
        "LOW", "LOW", "hypothesis/experiment ledger tests",
    ),
    AdoptionRow(
        "FinRL-X", "modular data/strategy/backtest interfaces",
        "strategy.evaluator + colab research jobs",
        AdoptionDecision.ADAPT,
        "Interface separation only; RL stays research challenger",
        "LOW", "MED", "challenger isolation tests",
    ),
    AdoptionRow(
        "TradingAgents", "multi-agent analyst/research/risk roles",
        "llm reasoning plane (post-mortem / critique)",
        AdoptionDecision.ADAPT,
        "Reasoning structure only; never financial SSOT",
        "NONE", "LOW", "llm_boundary validation",
    ),
    AdoptionRow(
        "FinRobot/FinGPT", "financial LLM research",
        "llm reasoning-only path",
        AdoptionDecision.REFERENCE,
        "Domain prompting ideas; not production decision engine",
        "NONE", "LOW", "anti-hallucination tests",
    ),
    AdoptionRow(
        "FinRL", "RL for trading",
        "research challenger (Colab)",
        AdoptionDecision.ADAPT,
        "Challenger research only; never Champion auto-swap",
        "HIGH", "HIGH", "PromotionGate blocks RL without authority",
    ),
    AdoptionRow(
        "vectorbt", "vectorized parameter / strategy search",
        "colab research jobs (hyperopt / sweep)",
        AdoptionDecision.ADAPT,
        "Colab-only compute; not GitHub Actions",
        "NONE", "MED", "job contract + budget tests",
    ),
    AdoptionRow(
        "skfolio", "portfolio opt / leakage-aware CV / online research",
        "research.regime_matrix + evaluator CV discipline",
        AdoptionDecision.ADAPT,
        "Leakage-aware CV principles; no full skfolio dependency",
        "LOW", "HIGH", "no-lookahead + time-split tests",
    ),
    AdoptionRow(
        "LEAN / Nautilus", "event-driven state / risk isolation",
        "ops paper path + risk gate",
        AdoptionDecision.REFERENCE,
        "Determinism & risk state principles; reject live execution",
        "NONE", "LOW", "paper-only safety tests",
    ),
    AdoptionRow(
        "Freqtrade / Jesse", "hyperopt / practical strategy engineering",
        "colab hyperopt job + experiment ledger",
        AdoptionDecision.ADAPT,
        "Hyperopt on Colab; FreqAI not in production path",
        "NONE", "MED", "experiment immutability tests",
    ),
    AdoptionRow(
        "Hummingbot", "strategy/controller/executor separation",
        "ops production_signal + risk + paper_portfolio",
        AdoptionDecision.REFERENCE,
        "Separation of concerns only; reject CEX connectors",
        "NONE", "LOW", "broker isolation tests",
    ),
    AdoptionRow(
        "Full Qlib/LEAN runtime", "vendor entire engine into IDX",
        "n/a",
        AdoptionDecision.REJECT,
        "Dependency/runtime/maintenance cost exceeds value",
        "HIGH", "MED", "n/a",
    ),
    AdoptionRow(
        "Online Champion mutation", "retrain-and-swap every trade",
        "n/a",
        AdoptionDecision.REJECT,
        "Violates PromotionGate + Champion immutability",
        "HIGH", "HIGH", "promotion negative-path tests",
    ),
    AdoptionRow(
        "Live / demo / dry-run broker", "external order submission",
        "n/a",
        AdoptionDecision.REJECT,
        "IDX is PAPER TRADING — INSTANT SIMULATION only",
        "HIGH", "LOW", "paper-only safety tests",
    ),
)


def matrix_as_dicts() -> list[dict[str, Any]]:
    return [
        {
            "source": r.source,
            "concept": r.concept,
            "idx_target": r.idx_target,
            "decision": r.decision.value,
            "rationale": r.rationale,
            "actions_cost": r.actions_cost,
            "leakage_risk": r.leakage_risk,
            "test_requirement": r.test_requirement,
        }
        for r in ADOPTION_MATRIX
    ]


def adopted_concepts() -> list[AdoptionRow]:
    return [r for r in ADOPTION_MATRIX if r.decision in (AdoptionDecision.ADOPT, AdoptionDecision.ADAPT)]
