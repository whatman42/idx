from src.python.ops.readiness import assess_readiness

def test_never_100pct_without_edge():
    r = assess_readiness(
        signal_bot_ok=True,
        paper_portfolio_ok=True,
        data_source="yfinance_public_research",
        dq_pass=True,
        freshness_status="PASS",
        cost_status="UNVERIFIED_ASSUMPTION",
        edge_status="UNVERIFIED",
        multi_day_paper_ok=True,
    )
    assert r.production_ready is False
    assert r.production_ready_100pct is False
    assert "economic_edge_not_demonstrated" in r.blockers

def test_synthetic_blocks_ops_data():
    r = assess_readiness(signal_bot_ok=True, paper_portfolio_ok=True, data_source="synthetic", dq_pass=True)
    assert r.data_operational == "SYNTHETIC_ONLY"

def test_100pct_only_with_full_evidence():
    r = assess_readiness(
        signal_bot_ok=True,
        paper_portfolio_ok=True,
        data_source="yfinance_public_research",
        dq_pass=True,
        freshness_status="PASS",
        cost_status="VERIFIED",
        edge_status="DEMONSTRATED",
        multi_day_paper_ok=True,
    )
    assert r.production_ready is True
    assert r.production_ready_100pct is True
