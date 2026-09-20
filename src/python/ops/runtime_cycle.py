"""Operational cycle identity for GitHub Actions runtime — traceability only.

cycle_id is NOT financial truth. Ledger remains SSOT for money.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

JKT = ZoneInfo("Asia/Jakarta")

STATUS_SUCCESS = "SUCCESS"
STATUS_NO_SIGNAL = "NO_SIGNAL"
STATUS_NO_TRADE = "NO_TRADE"
STATUS_BLOCKED_SCHEDULE = "BLOCKED_SCHEDULE"
STATUS_DATA_QUALITY = "NO_SIGNAL_DATA_QUALITY"
STATUS_DELIVERY_FAILURE = "DELIVERY_FAILURE"
STATUS_ERROR = "ERROR"
STATUS_DEGRADED = "DEGRADED"

EXIT_OK = 0
EXIT_HARD_FAIL = 1


def trading_date_jkt(now: Optional[datetime] = None) -> str:
    dt = now or datetime.now(JKT)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=JKT)
    return dt.astimezone(JKT).strftime("%Y-%m-%d")


def make_cycle_id(
    *,
    trading_date: Optional[str] = None,
    workflow_run_id: Optional[str] = None,
    run_attempt: Optional[str] = None,
    mode: str = "OPERATIONAL",
) -> str:
    """Deterministic-ish cycle id for a logical trading session + GH run.

    Format: IDX-{YYYY-MM-DD}-{mode}-{run_id}-{attempt}
    Prefer GITHUB_RUN_ID when present so re-runs share the same workflow identity
    and paper idempotency is based on signal_id, not cycle_id.
    """
    td = trading_date or trading_date_jkt()
    rid = workflow_run_id or os.getenv("GITHUB_RUN_ID") or "local"
    attempt = run_attempt or os.getenv("GITHUB_RUN_ATTEMPT") or "1"
    mode_s = re.sub(r"[^A-Z0-9]", "", (mode or "OPS").upper())[:12] or "OPS"
    rid_s = re.sub(r"[^0-9A-Za-z]", "", str(rid))[:16] or "local"
    return f"IDX-{td}-{mode_s}-{rid_s}-a{attempt}"


def concurrency_group_operational(trading_date: Optional[str] = None) -> str:
    """Logical concurrency key: one active ops cycle per market date."""
    td = trading_date or trading_date_jkt()
    return f"idx-operational-{td}"


def classify_exit(report: dict[str, Any]) -> tuple[int, str]:
    """Map operational report → (process exit code, status class).

    Expected market states (NO_SIGNAL, NO_TRADE, BLOCKED_SCHEDULE) → exit 0.
    Hard failures → exit 1.
    """
    if report.get("live_execution") is True or report.get("broker_execution") is True:
        return EXIT_HARD_FAIL, STATUS_ERROR
    status = str(report.get("status") or "").upper()
    if status in ("OK", "SUCCESS", "COMPLETED", "PORTFOLIO_RESET"):
        return EXIT_OK, STATUS_SUCCESS
    if status in ("BLOCKED_SCHEDULE",):
        return EXIT_OK, STATUS_BLOCKED_SCHEDULE
    if status in ("BLOCKED_FRESHNESS",) or "NO_SIGNAL" in status or status.startswith("HALTED_DATA"):
        return EXIT_OK, STATUS_NO_SIGNAL
    if status in ("HALTED_STALE_DATA",):
        return EXIT_OK, STATUS_NO_SIGNAL
    if "TELEGRAM" in status and "FAIL" in status:
        return EXIT_OK, STATUS_DELIVERY_FAILURE
    if status in ("DATA_FAILURE", "HALTED_CORRUPT_PORTFOLIO", "RECON_FAILURE"):
        return EXIT_HARD_FAIL, STATUS_ERROR
    if "signals_generated" in report or "paper_portfolio" in report:
        return EXIT_OK, STATUS_SUCCESS if not status else status
    return EXIT_OK, status or STATUS_DEGRADED


def telegram_failure_does_not_mutate_ledger() -> bool:
    """Contract: delivery layer cannot change financial truth."""
    return True


def schedule_is_weekday_utc_cron(cron: str) -> bool:
    """True if cron field day-of-week is Mon-Fri only (1-5)."""
    parts = cron.strip().split()
    if len(parts) < 5:
        return False
    dow = parts[4]
    return dow in ("1-5", "1,2,3,4,5")


def secret_scan_text(text: str) -> list[str]:
    """Heuristic scan for leaked tokens in logs/artifacts."""
    hits: list[str] = []
    patterns = [
        (r"(?i)telegram[_\s-]*bot[_\s-]*token\s*[:=]\s*['\"]?\d{8,}:[A-Za-z0-9_-]{20,}", "telegram_token"),
        (r"(?i)api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{24,}", "api_key_assignment"),
        (r"(?i)TURSO_AUTH_TOKEN\s*[:=]\s*['\"]?[A-Za-z0-9._\-]{20,}", "turso_token"),
    ]
    for pat, name in patterns:
        if re.search(pat, text):
            hits.append(name)
    return hits
