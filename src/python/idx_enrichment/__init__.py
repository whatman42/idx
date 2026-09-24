"""IDX / BEI enrichment plane — market structure support, CA, liquidity, sector.

Authority: see authority.AUTHORITY_MATRIX.
No live idx.co.id scrape as production SSOT.
"""
from src.python.idx_enrichment.authority import AUTHORITY_MATRIX, authority_for
from src.python.idx_enrichment.event_guard import evaluate_corporate_actions
from src.python.idx_enrichment.liquidity_gate import evaluate_liquidity
from src.python.idx_enrichment.models import (
    CorporateActionEvent,
    CorporateActionType,
    DataAuthority,
    EnrichmentDecision,
    FinancialSnapshot,
    LiquiditySnapshot,
    SectorSnapshot,
)
from src.python.idx_enrichment.pipeline import decisions_summary, pre_entry_enrichment_gates
from src.python.idx_enrichment.provider import IdxEnrichmentProvider, get_default_provider, set_default_provider
from src.python.idx_enrichment.sector_risk import evaluate_sector_add, sector_exposure

__all__ = [
    "AUTHORITY_MATRIX",
    "authority_for",
    "evaluate_corporate_actions",
    "evaluate_liquidity",
    "evaluate_sector_add",
    "sector_exposure",
    "CorporateActionEvent",
    "CorporateActionType",
    "DataAuthority",
    "EnrichmentDecision",
    "FinancialSnapshot",
    "LiquiditySnapshot",
    "SectorSnapshot",
    "pre_entry_enrichment_gates",
    "decisions_summary",
    "IdxEnrichmentProvider",
    "get_default_provider",
    "set_default_provider",
]
