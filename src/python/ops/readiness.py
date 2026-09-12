"""Honest production readiness assessment.

Never sets economic edge to VERIFIED without evidence.
Never claims live trading readiness.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class ReadinessReport:
    ops_signal_pipeline: str = "UNKNOWN"
    paper_portfolio: str = "UNKNOWN"
    data_operational: str = "UNKNOWN"
    freshness_gate: str = "UNKNOWN"
    cost_model: str = "UNVERIFIED_ASSUMPTION"
    economic_edge: str = "UNVERIFIED"
    live_trading: str = "NOT_SUPPORTED"
    production_ready: bool = False
    production_ready_100pct: bool = False
    blockers: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def assess_readiness(
    *,
    signal_bot_ok: bool = False,
    paper_portfolio_ok: bool = False,
    data_source: str = "",
    dq_pass: bool = False,
    freshness_status: str = "",
    cost_status: str = "UNVERIFIED_ASSUMPTION",
    edge_status: str = "UNVERIFIED",
    net_expectancy_after_cost: Optional[float] = None,
    multi_day_paper_ok: bool = False,
) -> ReadinessReport:
    r = ReadinessReport()
    r.ops_signal_pipeline = "PASS" if signal_bot_ok else "FAIL"
    r.paper_portfolio = "PASS" if paper_portfolio_ok else "FAIL"
    r.cost_model = cost_status
    r.economic_edge = edge_status
    r.live_trading = "NOT_SUPPORTED"

    src = (data_source or "").lower()
    if "synthetic" in src:
        r.data_operational = "SYNTHETIC_ONLY"
        r.blockers.append("data_is_synthetic_not_operational")
    elif "yfinance" in src or "csv" in src or "public" in src:
        r.data_operational = "PASS" if dq_pass else "FAIL"
        if not dq_pass:
            r.blockers.append("data_quality_failed")
    else:
        r.data_operational = "FAIL"
        r.blockers.append("no_operational_data_source")

    if freshness_status == "PASS":
        r.freshness_gate = "PASS"
    elif freshness_status in ("", "UNKNOWN"):
        r.freshness_gate = "UNKNOWN"
        r.blockers.append("freshness_not_evaluated")
    else:
        r.freshness_gate = "BLOCKED"
        r.notes.append(f"freshness={freshness_status}")

    if cost_status != "VERIFIED":
        r.blockers.append("cost_model_unverified")
    if edge_status not in ("VERIFIED_POSITIVE", "DEMONSTRATED"):
        r.blockers.append("economic_edge_not_demonstrated")
    if net_expectancy_after_cost is not None and net_expectancy_after_cost <= 0:
        r.blockers.append("net_expectancy_non_positive")
        r.economic_edge = "NOT_DEMONSTRATED"
    if not multi_day_paper_ok:
        r.notes.append("multi_day_paper_not_yet_proven_in_ops")

    ops_ok = (
        r.ops_signal_pipeline == "PASS"
        and r.paper_portfolio == "PASS"
        and r.data_operational in ("PASS", "SYNTHETIC_ONLY")
    )
    r.notes.append("ops_paper_pipeline_ok" if ops_ok else "ops_paper_pipeline_incomplete")

    r.production_ready_100pct = False
    r.production_ready = False
    if (
        r.ops_signal_pipeline == "PASS"
        and r.paper_portfolio == "PASS"
        and r.data_operational == "PASS"
        and r.freshness_gate == "PASS"
        and edge_status in ("VERIFIED_POSITIVE", "DEMONSTRATED")
        and cost_status == "VERIFIED"
    ):
        r.production_ready = True
        r.production_ready_100pct = True
        r.blockers = []
    else:
        r.production_ready = False
        r.production_ready_100pct = False

    return r
