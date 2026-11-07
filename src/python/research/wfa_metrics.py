"""Research-plane WFA / evidence metrics (2025–2026 validation practices).

Pure helpers — never mutate paper ledger, never auto-promote, never LIVE.

Metrics:
  - decay_ratio = OOS / IS (Sharpe or expectancy); interpret band
  - fold validity (VALID vs NO_TRADES) — ratios exclude zero-trade folds
  - buy-and-hold benchmark from close series
  - cost sensitivity: simulation vs IDX broker structure adapter

Production path (SMA20 / paper ops) is unchanged by importing these helpers.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence


DECAY_STRONG = 0.7
DECAY_ACCEPTABLE = 0.5
DECAY_WEAK = 0.3


def decay_ratio(
    oos_value: Optional[float],
    is_value: Optional[float],
    *,
    eps: float = 1e-12,
) -> Optional[float]:
    """OOS / IS ratio. None if IS missing or ~0 (avoid fake infinity)."""
    if oos_value is None or is_value is None:
        return None
    try:
        oos = float(oos_value)
        ins = float(is_value)
    except (TypeError, ValueError):
        return None
    if abs(ins) < eps:
        return None
    return float(oos / ins)


def classify_decay(ratio: Optional[float]) -> str:
    if ratio is None:
        return "UNKNOWN"
    if ratio >= DECAY_STRONG:
        return "STRONG"
    if ratio >= DECAY_ACCEPTABLE:
        return "ACCEPTABLE"
    if ratio >= DECAY_WEAK:
        return "WEAK"
    return "POOR"


def train_oos_degradation(
    train_value: Optional[float],
    oos_value: Optional[float],
    *,
    eps: float = 1e-9,
) -> Optional[float]:
    """(train - oos) / max(|train|, eps) — matches existing evaluator convention."""
    if train_value is None or oos_value is None:
        return None
    try:
        t = float(train_value)
        o = float(oos_value)
    except (TypeError, ValueError):
        return None
    return float((t - o) / max(abs(t), eps))


def buy_hold_total_return(closes: Sequence[float]) -> Optional[float]:
    """Simple buy-and-hold total return from first to last close (no costs)."""
    if not closes or len(closes) < 2:
        return None
    try:
        c0 = float(closes[0])
        c1 = float(closes[-1])
    except (TypeError, ValueError, IndexError):
        return None
    if c0 <= 0:
        return None
    return float(c1 / c0 - 1.0)


def strategy_vs_buyhold(
    strategy_total_return: Optional[float],
    buyhold_total_return: Optional[float],
) -> dict[str, Any]:
    """Compare strategy net-ish return to passive buy-hold (research only)."""
    out: dict[str, Any] = {
        "strategy_total_return": strategy_total_return,
        "buyhold_total_return": buyhold_total_return,
        "excess_vs_buyhold": None,
        "beats_buyhold": None,
        "note": "Buy-hold is uncosted close-to-close; strategy should be cost-adjusted when available.",
    }
    if strategy_total_return is None or buyhold_total_return is None:
        return out
    try:
        s = float(strategy_total_return)
        b = float(buyhold_total_return)
    except (TypeError, ValueError):
        return out
    excess = s - b
    out["excess_vs_buyhold"] = float(excess)
    out["beats_buyhold"] = bool(excess > 0)
    return out


def enrich_oos_research_metrics(
    *,
    is_expectancy: Optional[float] = None,
    oos_expectancy: Optional[float] = None,
    is_sharpe: Optional[float] = None,
    oos_sharpe: Optional[float] = None,
    train_to_oos_degradation: Optional[float] = None,
    strategy_total_return: Optional[float] = None,
    buyhold_total_return: Optional[float] = None,
) -> dict[str, Any]:
    """Bundle decay + benchmark for EvidencePackage / manual_review.json."""
    exp_decay = decay_ratio(oos_expectancy, is_expectancy)
    sh_decay = decay_ratio(oos_sharpe, is_sharpe)
    primary = exp_decay if exp_decay is not None else sh_decay
    deg = train_to_oos_degradation
    if deg is None and is_expectancy is not None and oos_expectancy is not None:
        deg = train_oos_degradation(is_expectancy, oos_expectancy)
    bh = strategy_vs_buyhold(strategy_total_return, buyhold_total_return)
    return {
        "schema": "research_wfa_metrics_v1",
        "plane": "RESEARCH_ONLY",
        "auto_promote": False,
        "decay_ratio_expectancy": exp_decay,
        "decay_ratio_sharpe": sh_decay,
        "decay_ratio_primary": primary,
        "decay_class": classify_decay(primary),
        "train_to_oos_degradation": deg,
        "thresholds": {
            "strong": DECAY_STRONG,
            "acceptable": DECAY_ACCEPTABLE,
            "weak": DECAY_WEAK,
        },
        "benchmark": bh,
        "interpretation": _interpret(primary, bh),
    }


def _interpret(decay: Optional[float], bh: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    cls = classify_decay(decay)
    if cls == "STRONG":
        notes.append("OOS/IS decay strong — still requires fold + symbol consistency before candidate review")
    elif cls == "ACCEPTABLE":
        notes.append("OOS/IS decay acceptable — manual review required; do not auto-promote")
    elif cls == "WEAK":
        notes.append("OOS/IS decay weak — prefer KEEP_SHADOW_RESEARCH or REQUEST_MORE_DATA")
    elif cls == "POOR":
        notes.append("OOS/IS decay poor — treat as curve-fit risk; reject promotion")
    else:
        notes.append("Decay unknown — insufficient IS/OOS pair")
    if bh.get("beats_buyhold") is False:
        notes.append("Strategy does not beat uncosted buy-hold on total return")
    elif bh.get("beats_buyhold") is True:
        notes.append("Strategy exceeds uncosted buy-hold on total return (verify costs applied)")
    notes.append("Never maps to PAPER_ALLOWED or LIVE_EXECUTION automatically")
    return notes


def cost_sensitivity_summary() -> dict[str, Any]:
    """Expose simulation vs IDX broker structure for research sensitivity tables."""
    from src.python.data.costs import default_broker_cost, default_paper_cost

    sim = default_paper_cost().to_dict()
    brk = default_broker_cost().to_dict()
    return {
        "schema": "cost_sensitivity_v1",
        "paper_path_uses": "SIMULATION",
        "simulation": sim,
        "idx_broker_adapter": brk,
        "rule": (
            "Paper/ops remain on SimulationCostModel. "
            "IDXBrokerCostModel is research sensitivity only until calibrated against real fills."
        ),
        "research_use": [
            "Re-run evaluator with broker adapter fee/slippage for sensitivity",
            "Do not switch production paper path without explicit lifecycle decision",
        ],
    }
