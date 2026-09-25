"""IDX enrichment facts → policy → PASS/BLOCK/REVIEW before Risk + MS Gate.

  OHLCV → validate → FeatureSnapshot → SMA20
       → IDX Enrichment (CA / Liquidity / Sector)  ← not strategy authority
       → Risk → Governor → Market Structure Gate → Paper → Ledger

Market structure / delisting / instrument status: ExecutionGate only (HARD).
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from src.python.idx_enrichment.event_guard import evaluate_corporate_actions
from src.python.idx_enrichment.liquidity_gate import evaluate_liquidity
from src.python.idx_enrichment.models import EnrichmentDecision
from src.python.idx_enrichment.policy import DEFAULT_POLICY, EnrichmentPolicy
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
    policy: Optional[EnrichmentPolicy] = None,
) -> tuple[bool, list[EnrichmentDecision]]:
    pol = policy or DEFAULT_POLICY
    prov = provider or get_default_provider()
    decisions: list[EnrichmentDecision] = []

    ca = evaluate_corporate_actions(symbol, trading_date, prov.events_for(symbol), policy=pol)
    decisions.append(ca)
    if not ca.allow:
        return False, decisions

    liq = evaluate_liquidity(
        symbol, prov.liquidity_for(symbol), trading_date=trading_date, policy=pol
    )
    decisions.append(liq)
    if not liq.allow:
        return False, decisions

    sec = evaluate_sector_add(
        symbol,
        proposed_weight,
        open_positions or {},
        prov.sectors,
        equity=equity,
        policy=pol,
    )
    decisions.append(sec)
    if not sec.allow:
        return False, decisions

    return True, decisions


def decisions_summary(decisions: list[EnrichmentDecision]) -> dict[str, Any]:
    return {
        "allow": all(d.allow for d in decisions),
        "strategy_authority": False,
        "layers": [d.to_dict() for d in decisions],
        "outcomes": [d.outcome for d in decisions],
        "presences": [d.presence for d in decisions],
    }
