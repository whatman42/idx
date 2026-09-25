"""IDX / BEI enrichment — facts + policy gates (not strategy authority).

NO_DATA is never silent PASS for corporate action (CA_REVIEW or BLOCK).
Market structure / delisting remain ExecutionGate HARD authority.
No live idx.co.id scrape as production SSOT.
"""
from src.python.idx_enrichment.authority import AUTHORITY_MATRIX, authority_for
from src.python.idx_enrichment.event_guard import evaluate_corporate_actions
from src.python.idx_enrichment.liquidity_gate import evaluate_liquidity
from src.python.idx_enrichment.models import (
    CAOutcome,
    CorporateActionEvent,
    CorporateActionType,
    DataAuthority,
    DataPresence,
    EnrichmentDecision,
    FinancialSnapshot,
    GateOutcome,
    LiquiditySnapshot,
    Provenance,
    SectorSnapshot,
)
from src.python.idx_enrichment.pipeline import decisions_summary, pre_entry_enrichment_gates
from src.python.idx_enrichment.policy import DEFAULT_POLICY, EnrichmentPolicy, resolve_presence
from src.python.idx_enrichment.provider import IdxEnrichmentProvider, get_default_provider, set_default_provider
from src.python.idx_enrichment.sector_risk import evaluate_sector_add, sector_exposure

__all__ = [
    "AUTHORITY_MATRIX",
    "authority_for",
    "evaluate_corporate_actions",
    "evaluate_liquidity",
    "evaluate_sector_add",
    "sector_exposure",
    "CAOutcome",
    "CorporateActionEvent",
    "CorporateActionType",
    "DataAuthority",
    "DataPresence",
    "EnrichmentDecision",
    "FinancialSnapshot",
    "GateOutcome",
    "LiquiditySnapshot",
    "Provenance",
    "SectorSnapshot",
    "pre_entry_enrichment_gates",
    "decisions_summary",
    "DEFAULT_POLICY",
    "EnrichmentPolicy",
    "resolve_presence",
    "IdxEnrichmentProvider",
    "get_default_provider",
    "set_default_provider",
]
