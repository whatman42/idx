"""Gate policy: maps (layer, DataPresence, constraint result) → PASS/BLOCK/REVIEW.

IDX cache supplies facts. Policy supplies operational consequences.
Market structure / instrument status remain HARD via ExecutionGate (separate).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from src.python.idx_enrichment.models import DataPresence


@dataclass(frozen=True)
class EnrichmentPolicy:
    ca_on_no_data: str = "REVIEW_ALLOW"  # REVIEW_ALLOW | BLOCK
    ca_on_stale: str = "REVIEW_ALLOW"
    ca_on_invalid: str = "BLOCK"
    ca_blackout_block: bool = True
    liquidity_required: bool = False
    liquidity_on_stale: str = "BLOCK"
    liquidity_on_invalid: str = "BLOCK"
    sector_on_no_data: str = "ALLOW"
    sector_on_stale: str = "ALLOW"
    sector_on_invalid: str = "ALLOW"
    max_stale_days: int = 14

    @classmethod
    def from_env(cls) -> "EnrichmentPolicy":
        liq_req = os.getenv("IDX_LIQUIDITY_REQUIRED", "").strip() in ("1", "true", "TRUE", "yes")
        ca_nd = os.getenv("IDX_CA_ON_NO_DATA", "REVIEW_ALLOW").strip().upper()
        if ca_nd not in ("REVIEW_ALLOW", "BLOCK"):
            ca_nd = "REVIEW_ALLOW"
        return cls(liquidity_required=liq_req, ca_on_no_data=ca_nd)


DEFAULT_POLICY = EnrichmentPolicy()


def resolve_presence(
    *,
    has_record: bool,
    as_of: str = "",
    trading_date: str = "",
    max_stale_days: int = 14,
    invalid: bool = False,
) -> DataPresence:
    if invalid:
        return DataPresence.INVALID
    if not has_record:
        return DataPresence.NO_DATA
    if as_of and trading_date:
        try:
            from datetime import datetime
            a = datetime.strptime(str(as_of)[:10], "%Y-%m-%d").date()
            t = datetime.strptime(str(trading_date)[:10], "%Y-%m-%d").date()
            if (t - a).days > max_stale_days:
                return DataPresence.STALE
        except ValueError:
            return DataPresence.INVALID
    return DataPresence.DATA_PRESENT
