"""Daily/weekend operational status taxonomy (observable, fail-closed)."""
from __future__ import annotations

from typing import Any

DAILY_KEYS = (
    "DATA_STATUS",
    "FEATURE_STATUS",
    "SIGNAL_STATUS",
    "RISK_STATUS",
    "GOVERNOR_STATUS",
    "PAPER_EXECUTION_STATUS",
    "LEDGER_STATUS",
    "RECON_STATUS",
    "TELEGRAM_STATUS",
)

RESEARCH_KEYS = (
    "DATASET_STATUS",
    "FEATURE_STATUS",
    "BACKTEST_STATUS",
    "WFA_STATUS",
    "TRAINING_STATUS",
    "EVIDENCE_STATUS",
    "PROMOTION_STATUS",
)


def empty_daily_status() -> dict[str, str]:
    return {k: "NOT_EVALUATED" for k in DAILY_KEYS}


def empty_research_status() -> dict[str, str]:
    return {k: "NOT_EVALUATED" for k in RESEARCH_KEYS}


def attach_daily_status(report: dict[str, Any], **statuses: str) -> dict[str, Any]:
    base = report.get("operational_status") or empty_daily_status()
    for k, v in statuses.items():
        key = k if k.endswith("_STATUS") else f"{k}_STATUS"
        if key in base or key in DAILY_KEYS:
            base[key] = str(v)
    report["operational_status"] = base
    return report
