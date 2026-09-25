"""IDX enrichment: CA event guard, liquidity, sector, pipeline."""
from __future__ import annotations

from src.python.idx_enrichment import (
    AUTHORITY_MATRIX,
    CorporateActionEvent,
    CorporateActionType,
    IdxEnrichmentProvider,
    LiquiditySnapshot,
    SectorSnapshot,
    evaluate_corporate_actions,
    evaluate_liquidity,
    evaluate_sector_add,
    pre_entry_enrichment_gates,
    set_default_provider,
)


def test_authority_matrix_has_hard_and_research():
    assert AUTHORITY_MATRIX["market_structure"]["authority"] == "HARD_GATE"
    assert AUTHORITY_MATRIX["corporate_action"]["authority"] == "CONDITIONAL_GATE"
    assert AUTHORITY_MATRIX["xbrl_financial"]["production"] is False
    assert AUTHORITY_MATRIX["ownership"]["authority"] == "INFORMATIONAL"


def test_ca_blackout_blocks_entry():
    ev = CorporateActionEvent(
        symbol="ABDA",
        action_type=CorporateActionType.DIVIDEND,
        ex_date="2026-09-25",
        cum_date="2026-09-24",
    )
    d = evaluate_corporate_actions("ABDA", "2026-09-25", [ev])
    assert d.allow is False
    assert d.reason == "DATA_EVENT_REVIEW"


def test_ca_outside_window_passes():
    ev = CorporateActionEvent(
        symbol="ABDA",
        action_type=CorporateActionType.DIVIDEND,
        ex_date="2026-08-01",
    )
    d = evaluate_corporate_actions("ABDA", "2026-09-25", [ev])
    assert d.allow is True
    assert d.reason == "PASS"


def test_ca_no_data_passes():
    d = evaluate_corporate_actions("ZZZZ", "2026-09-25", [])
    assert d.allow is True
    assert d.reason == "NO_DATA"


def test_liquidity_below_threshold_blocks():
    snap = LiquiditySnapshot(
        symbol="ILLQ", as_of="2026-09-24", avg_value=1_000_000, avg_volume=1000, trading_days=10
    )
    d = evaluate_liquidity("ILLQ", snap)
    assert d.allow is False
    assert d.reason == "SKIPPED_LIQUIDITY"


def test_liquidity_no_data_passes():
    d = evaluate_liquidity("BBCA", None)
    assert d.allow is True
    assert d.reason == "NO_LIQ_DATA"


def test_sector_concentration_blocks():
    sectors = {
        "A": SectorSnapshot(symbol="A", sector="Energy"),
        "B": SectorSnapshot(symbol="B", sector="Energy"),
        "C": SectorSnapshot(symbol="C", sector="Energy"),
    }
    open_pos = {
        "A": {"qty": 1000, "avg_entry": 1000},
        "B": {"qty": 1000, "avg_entry": 1000},
    }
    equity = 10_000_000
    d = evaluate_sector_add("C", 0.20, open_pos, sectors, equity=equity)
    assert d.allow is False
    assert "SECTOR" in d.reason


def test_pipeline_ca_blocks_before_liquidity():
    prov = IdxEnrichmentProvider(
        corporate_actions=[
            CorporateActionEvent(
                symbol="X",
                action_type=CorporateActionType.STOCK_SPLIT,
                effective_date="2026-09-25",
            )
        ]
    )
    ok, decisions = pre_entry_enrichment_gates(
        "X", "2026-09-25", proposed_weight=0.05, equity=1e7, provider=prov
    )
    assert ok is False
    assert decisions[0].reason == "DATA_EVENT_REVIEW"
    assert len(decisions) == 1


def test_pipeline_empty_provider_allows():
    set_default_provider(IdxEnrichmentProvider())
    ok, decisions = pre_entry_enrichment_gates("BBCA", "2026-09-25", proposed_weight=0.05, equity=1e7)
    assert ok is True
    assert all(d.allow for d in decisions)


def test_provider_from_dict():
    prov = IdxEnrichmentProvider.from_dict(
        {
            "as_of": "2026-09-24",
            "corporate_actions": [
                {"symbol": "TLKM", "action_type": "DIVIDEND", "ex_date": "2026-09-20"}
            ],
            "liquidity": {"TLKM": {"avg_value": 1e11, "avg_volume": 1e7, "trading_days": 20}},
            "sectors": {"TLKM": {"sector": "Infrastructure", "subsector": "Telecommunication"}},
        }
    )
    assert len(prov.events_for("TLKM")) == 1
    assert prov.liquidity_for("TLKM").avg_value > 0
    assert prov.sector_for("TLKM").sector == "Infrastructure"
