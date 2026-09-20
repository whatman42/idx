"""Static inventory of external research dependencies."""
from __future__ import annotations

from typing import Any


INVENTORY: list[dict[str, Any]] = [
    {
        "dependency": "Turso/libSQL",
        "purpose": "Research/learning memory",
        "read_write": "R/W",
        "required": False,
        "failure_modes": ["UNAVAILABLE", "AUTH_ERROR", "NETWORK_ERROR", "TIMEOUT"],
        "fallback": "SQLite :memory: or MEMORY_UNAVAILABLE; continue without memory",
        "can_continue_research": True,
        "can_promote": False,
        "can_affect_ledger": False,
    },
    {
        "dependency": "SQLite (local)",
        "purpose": "Offline/test research memory",
        "read_write": "R/W",
        "required": False,
        "failure_modes": ["CONFIG_ERROR"],
        "fallback": "MEMORY_UNAVAILABLE",
        "can_continue_research": True,
        "can_promote": False,
        "can_affect_ledger": False,
    },
    {
        "dependency": "Google Colab",
        "purpose": "Heavy research compute (WFA/ML)",
        "read_write": "compute",
        "required": True,
        "failure_modes": ["UNAVAILABLE", "TIMEOUT", "INCOMPLETE", "ARTIFACT_MISSING"],
        "fallback": "QUEUE/BLOCK; never heavy WFA on Actions",
        "can_continue_research": False,
        "can_promote": False,
        "can_affect_ledger": False,
    },
    {
        "dependency": "Google Drive",
        "purpose": "Optional artifact storage",
        "read_write": "R/W",
        "required": False,
        "failure_modes": ["AUTH_ERROR", "ARTIFACT_MISSING", "ARTIFACT_CORRUPT", "TIMEOUT"],
        "fallback": "ARTIFACT_STORAGE_DEGRADED; no dummy artifacts",
        "can_continue_research": True,
        "can_promote": False,
        "can_affect_ledger": False,
    },
    {
        "dependency": "Gemini/LLM",
        "purpose": "Optional reasoning/interpretation",
        "read_write": "R",
        "required": False,
        "failure_modes": ["UNAVAILABLE", "TIMEOUT", "AUTH_ERROR"],
        "fallback": "LLM_UNAVAILABLE; no fabricated interpretation; never numeric truth",
        "can_continue_research": True,
        "can_promote": False,
        "can_affect_ledger": False,
    },
    {
        "dependency": "yfinance / market data",
        "purpose": "OHLCV research inputs",
        "read_write": "R",
        "required": True,
        "failure_modes": ["DATA_STALE", "DATA_INVALID", "NETWORK_ERROR", "TIMEOUT"],
        "fallback": "BLOCK research; no guessed prices",
        "can_continue_research": False,
        "can_promote": False,
        "can_affect_ledger": False,
    },
    {
        "dependency": "GitHub API (publish)",
        "purpose": "Optional candidate artifact publish",
        "read_write": "W",
        "required": False,
        "failure_modes": ["AUTH_ERROR", "NETWORK_ERROR", "TIMEOUT"],
        "fallback": "record error; never promote",
        "can_continue_research": True,
        "can_promote": False,
        "can_affect_ledger": False,
    },
    {
        "dependency": "GitHub Actions",
        "purpose": "Cheap control plane",
        "read_write": "orchestrate",
        "required": False,
        "failure_modes": ["TIMEOUT", "CONFIG_ERROR"],
        "fallback": "no heavy WFA; scheduler retry only",
        "can_continue_research": True,
        "can_promote": False,
        "can_affect_ledger": False,
    },
]


def inventory_table() -> list[dict[str, Any]]:
    return list(INVENTORY)
