"""Authority matrix for IDX enrichment data planes."""
from __future__ import annotations

from src.python.idx_enrichment.models import DataAuthority

AUTHORITY_MATRIX: dict[str, dict] = {
    "market_structure": {
        "authority": DataAuthority.HARD_GATE.value,
        "function": "Instrument/order validity",
        "production": True,
        "fail_closed_when_unknown": True,
    },
    "trading_status": {
        "authority": DataAuthority.HARD_GATE.value,
        "function": "Block invalid trading conditions",
        "production": True,
        "fail_closed_when_unknown": True,
    },
    "corporate_action": {
        "authority": DataAuthority.CONDITIONAL_GATE.value,
        "function": "Event protection around CA dates",
        "production": True,
        "fail_closed_when_unknown": False,
    },
    "liquidity": {
        "authority": DataAuthority.RISK_GATE.value,
        "function": "Tradability / min liquidity constraint",
        "production": True,
        "fail_closed_when_unknown": False,
    },
    "sector": {
        "authority": DataAuthority.RISK_GATE.value,
        "function": "Concentration analysis",
        "production": True,
        "fail_closed_when_unknown": False,
    },
    "xbrl_financial": {
        "authority": DataAuthority.RESEARCH.value,
        "function": "Fundamental features",
        "production": False,
        "fail_closed_when_unknown": False,
    },
    "ownership": {
        "authority": DataAuthority.INFORMATIONAL.value,
        "function": "Context only (KSEI provenance caveat)",
        "production": False,
        "fail_closed_when_unknown": False,
    },
    "public_expose": {
        "authority": DataAuthority.INFORMATIONAL.value,
        "function": "Research context",
        "production": False,
        "fail_closed_when_unknown": False,
    },
}


def authority_for(plane: str) -> str:
    row = AUTHORITY_MATRIX.get(plane) or {}
    return str(row.get("authority") or DataAuthority.INFORMATIONAL.value)


def is_production_plane(plane: str) -> bool:
    row = AUTHORITY_MATRIX.get(plane) or {}
    return bool(row.get("production"))
