"""IDX enrichment pipeline order (paper path):

  FeatureSnapshot / Signal
        ↓
  Corporate Action Event Guard
        ↓
  Liquidity Gate
        ↓
  Sector concentration (soft)
        ↓
  Risk Gate (existing)
        ↓
  Market Structure ExecutionGate (existing)
        ↓
  Paper fill

LIVE_EXECUTION remains FALSE. No broker calls.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from src.python.idx_enrichment.event_guard import evaluate_corporate_actions
from src.python.idx_enrichment.liquidity_gate import evaluate_liquidity
from src.python.idx_enrichment.models import EnrichmentDecision
from src.python.idx_enrichment.provider import IdxEnrichmentProvider, get_default_provider
from src.python.idx_enrichment.sector_risk import evaluate_sector_add


def pre_entry_enrichment_gates(
    symbol: str,
    trading_date: str,
    *,
    proposed_weight: float = 0.0,
    open_positions: Optional[Mapping[str, dict]] = None,
    equity: float = 0.0,
    provider: Optional[IdxEnrichmentProvider] = None,
) -> tuple[bool, list[EnrichmentDecision]]:
    """Run CA → Liquidity → Sector. First blocking decision stops further soft gates."""
    prov = provider or get_default_provider()
    decisions: list[EnrichmentDecision] = []

    ca = evaluate_corporate_actions(symbol, trading_date, prov.events_for(symbol))
    decisions.append(ca)
    if not ca.allow:
        return False, decisions

    liq = evaluate_liquidity(symbol, prov.liquidity_for(symbol))
    decisions.append(liq)
    if not liq.allow:
        return False, decisions

    sec = evaluate_sector_add(
        symbol,
        proposed_weight,
        open_positions or {},
        prov.sectors,
        equity=equity,
    )
    decisions.append(sec)
    if not sec.allow:
        return False, decisions

    return True, decisions


def decisions_summary(decisions: list[EnrichmentDecision]) -> dict[str, Any]:
    return {
        "allow": all(d.allow for d in decisions),
        "layers": [d.to_dict() for d in decisions],
    }
