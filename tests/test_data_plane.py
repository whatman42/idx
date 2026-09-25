"""Data plane role split: OHLCV convenience vs IDX reference authority."""
from __future__ import annotations

import pytest

from src.python.data_plane import (
    DATA_PLANE_ROLES,
    ROLE_IDX_REFERENCE,
    ROLE_MARKET_DATA,
    assert_no_live_idx_scrape,
    describe_data_plane,
)


def test_roles_split_ohlcv_vs_idx():
    md = DATA_PLANE_ROLES[ROLE_MARKET_DATA]
    ref = DATA_PLANE_ROLES[ROLE_IDX_REFERENCE]
    assert "yfinance_public_research" in md["primary_providers"]
    assert "corporate_action_bei" in md["not_authority_for"]
    assert "corporate_action" in ref["authority_for"]
    assert ref["live_website_scrape"] is False


def test_describe_pipeline_order():
    d = describe_data_plane()
    assert d["live_execution"] is False
    assert "FeatureSnapshot" in d["pipeline"]
    assert d["pipeline"][0] == "MARKET_DATA_OHLCV"


def test_no_live_scrape_invariant():
    assert_no_live_idx_scrape(live_scrape_flag=False)
    with pytest.raises(RuntimeError, match="LIVE_IDX_SCRAPE_FORBIDDEN"):
        assert_no_live_idx_scrape(live_scrape_flag=True)
