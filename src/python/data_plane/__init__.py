"""DATA PLANE — dual-source architecture for IDX paper bot.

    Market Data (OHLCV)              IDX Reference / Metadata
    yfinance / CSV / synthetic       local certified cache (not live scrape)
           │                                    │
           │                         Structure · CA · Liquidity · Sector · XBRL*
           └────────────────┬───────────────────┘
                            ↓
                   FeatureSnapshot SSOT
                            ↓
                      Signal / Ranking
                            ↓
                     Risk + IDX enrichment gates
                            ↓
                   Market Structure Gate
                            ↓
                      Paper Execution → Ledger

* XBRL = RESEARCH only until publication_timestamp PIT is certified.

yfinance does NOT replace IDX for market-structure authority.
IDX does NOT replace yfinance for convenient historical OHLCV.

LIVE scrape of idx.co.id is FORBIDDEN as production dependency.
"""
from src.python.data_plane.roles import (
    DATA_PLANE_ROLES,
    ROLE_IDX_REFERENCE,
    ROLE_MARKET_DATA,
    assert_no_live_idx_scrape,
    describe_data_plane,
)

__all__ = [
    "DATA_PLANE_ROLES",
    "ROLE_MARKET_DATA",
    "ROLE_IDX_REFERENCE",
    "describe_data_plane",
    "assert_no_live_idx_scrape",
]
