"""Explicit role split: market-data convenience vs IDX reference authority."""
from __future__ import annotations

from typing import Any

ROLE_MARKET_DATA = "MARKET_DATA_OHLCV"
ROLE_IDX_REFERENCE = "IDX_REFERENCE_METADATA"

DATA_PLANE_ROLES: dict[str, dict[str, Any]] = {
    ROLE_MARKET_DATA: {
        "purpose": "Historical OHLCV for features, signals, marks, backtest",
        "primary_providers": ["yfinance_public_research", "csv", "synthetic"],
        "not_authority_for": [
            "instrument_status",
            "delisting",
            "corporate_action_bei",
            "idx_ic_sector",
            "market_structure_session",
            "xbrl_disclosure",
        ],
        "production_ok": True,
        "notes": "Convenient; not official BEI. auto_adjust and gaps must be documented.",
    },
    ROLE_IDX_REFERENCE: {
        "purpose": "Indonesian market authority / enrichment",
        "primary_providers": ["idx_enrichment_local_cache"],
        "authority_for": [
            "instrument_status",
            "corporate_action",
            "liquidity_statistics",
            "sector_idx_ic",
            "index_membership",
            "market_structure",
        ],
        "research_only": ["xbrl_financial", "ownership", "public_expose"],
        "production_ok": True,
        "live_website_scrape": False,
        "notes": (
            "Cache + provenance only. IDX website ToS: as-is, no scraping for bulk use. "
            "Do not fail-closed on empty cache until feed is certified."
        ),
    },
}


def describe_data_plane() -> dict[str, Any]:
    return {
        "version": "data_plane_v1",
        "live_execution": False,
        "broker_execution": False,
        "ohlcv_ssot": "provider-labeled DataContract (yfinance/csv/synthetic)",
        "feature_ssot": "FeatureSnapshot",
        "portfolio_ssot": "paper ledger",
        "idx_reference_ssot": "data/idx/enrichment_cache.json or IDX_ENRICHMENT_CACHE",
        "roles": DATA_PLANE_ROLES,
        "pipeline": [
            "MARKET_DATA_OHLCV",
            "IDX_REFERENCE_METADATA",
            "FeatureSnapshot",
            "Signal/Ranking",
            "Risk + CA/Liquidity/Sector gates",
            "MarketStructure ExecutionGate",
            "Paper fill",
            "Ledger",
        ],
    }


def assert_no_live_idx_scrape(*, live_scrape_flag: bool = False) -> None:
    """Hard invariant: production must not depend on live idx.co.id crawl."""
    if live_scrape_flag:
        raise RuntimeError(
            "LIVE_IDX_SCRAPE_FORBIDDEN: IDX website is not production SSOT; "
            "use certified local cache (IdxEnrichmentProvider)."
        )
