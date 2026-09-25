"""IDX enrichment: presence semantics, CA outcomes, liquidity policy, pipeline."""
from __future__ import annotations

from src.python.idx_enrichment import (
    AUTHORITY_MATRIX,
    CAOutcome,
    CorporateActionEvent,
    CorporateActionType,
    DataPresence,
    EnrichmentPolicy,
    IdxEnrichmentProvider,
    LiquiditySnapshot,
    Provenance,
    SectorSnapshot,
    evaluate_corporate_actions,
    evaluate_liquidity,
    evaluate_sector_add,
    pre_entry_enrichment_gates,
    set_default_provider,
)
from src.python.market_structure import ExecutionGate
from src.python.market_structure.provider import MarketStructureProvider


def test_authority_matrix():
    assert AUTHORITY_MATRIX["corporate_action"]["authority"] == "CONDITIONAL_GATE"
    assert AUTHORITY_MATRIX["market_structure"]["fail_closed_when_unknown"] is True


def test_ca_no_data_is_review_not_silent_pass():
    d = evaluate_corporate_actions("ZZZZ", "2026-09-25", [])
    assert d.allow is True
    assert d.outcome == CAOutcome.CA_REVIEW.value
    assert d.presence == DataPresence.NO_DATA.value
    assert d.reason == "CA_NO_DATA_REVIEW"
    assert "CLEAR" not in d.outcome


def test_ca_no_data_block_policy():
    pol = EnrichmentPolicy(ca_on_no_data="BLOCK")
    d = evaluate_corporate_actions("ZZZZ", "2026-09-25", [], policy=pol)
    assert d.allow is False
    assert d.outcome == CAOutcome.CA_BLOCK.value


def test_ca_blackout_block():
    ev = CorporateActionEvent(
        symbol="ABDA",
        action_type=CorporateActionType.DIVIDEND,
        ex_date="2026-09-25",
        provenance=Provenance(symbol="ABDA", as_of="2026-09-24", status="OK"),
    )
    d = evaluate_corporate_actions("ABDA", "2026-09-25", [ev])
    assert d.allow is False
    assert d.outcome == CAOutcome.CA_BLOCK.value
    assert d.reason == "CA_BLACKOUT"


def test_ca_clear_outside_window():
    ev = CorporateActionEvent(
        symbol="ABDA",
        action_type=CorporateActionType.DIVIDEND,
        ex_date="2026-08-01",
        provenance=Provenance(symbol="ABDA", as_of="2026-09-20", status="OK"),
    )
    d = evaluate_corporate_actions("ABDA", "2026-09-25", [ev])
    assert d.allow is True
    assert d.outcome == CAOutcome.CA_CLEAR.value


def test_ca_never_emits_trade_decision():
    for events in ([], [CorporateActionEvent("X", CorporateActionType.DIVIDEND, ex_date="2026-09-25")]):
        d = evaluate_corporate_actions("X", "2026-09-25", events)
        assert d.outcome not in ("BUY", "SELL", "HOLD")


def test_liquidity_no_data_optional_pass():
    d = evaluate_liquidity("BBCA", None)
    assert d.allow is True
    assert d.presence == DataPresence.NO_DATA.value
    assert d.reason == "LIQUIDITY_NO_DATA_OPTIONAL"


def test_liquidity_no_data_required_blocks():
    pol = EnrichmentPolicy(liquidity_required=True)
    d = evaluate_liquidity("BBCA", None, policy=pol)
    assert d.allow is False
    assert d.reason == "LIQUIDITY_NO_DATA_REQUIRED"


def test_liquidity_below_threshold_blocks():
    snap = LiquiditySnapshot(
        symbol="ILLQ", as_of="2026-09-24", avg_value=1_000_000, avg_volume=1000, trading_days=10
    )
    d = evaluate_liquidity("ILLQ", snap, trading_date="2026-09-25")
    assert d.allow is False
    assert d.reason == "SKIPPED_LIQUIDITY"


def test_sector_no_data_continues():
    d = evaluate_sector_add("Z", 0.05, {}, {}, equity=1e7)
    assert d.allow is True
    assert d.presence == DataPresence.NO_DATA.value


def test_pipeline_ca_review_allows_entry():
    set_default_provider(IdxEnrichmentProvider())
    ok, decs = pre_entry_enrichment_gates("BBCA", "2026-09-25", proposed_weight=0.05, equity=1e7)
    assert ok is True
    assert decs[0].outcome == CAOutcome.CA_REVIEW.value


def test_pipeline_ca_block_short_circuits():
    prov = IdxEnrichmentProvider(
        corporate_actions=[
            CorporateActionEvent(
                symbol="X",
                action_type=CorporateActionType.STOCK_SPLIT,
                effective_date="2026-09-25",
                provenance=Provenance(symbol="X", as_of="2026-09-24"),
            )
        ]
    )
    ok, decs = pre_entry_enrichment_gates(
        "X", "2026-09-25", proposed_weight=0.05, equity=1e7, provider=prov
    )
    assert ok is False
    assert decs[0].outcome == CAOutcome.CA_BLOCK.value
    assert len(decs) == 1


def test_market_structure_gate_still_hard_authority():
    prov = MarketStructureProvider({})
    gate = ExecutionGate(provider=prov, require_price_rules=False, require_open_session=False)
    r = gate.check_symbol("UNKNOWN_SYM")
    assert r.allow is False


def test_provider_provenance_fields():
    prov = IdxEnrichmentProvider.from_dict(
        {
            "as_of": "2026-09-24",
            "corporate_actions": [
                {
                    "symbol": "TLKM",
                    "action_type": "DIVIDEND",
                    "ex_date": "2026-09-20",
                    "retrieved_at": "2026-09-21T00:00:00Z",
                    "version": "2",
                }
            ],
        }
    )
    ev = prov.events_for("TLKM")[0]
    assert ev.provenance.retrieved_at.startswith("2026")
    assert ev.provenance.version == "2"
    assert ev.provenance.symbol == "TLKM"
