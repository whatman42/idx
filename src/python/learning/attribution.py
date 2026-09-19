"""Outcome Attribution Engine — explain why a trade won or lost."""
from __future__ import annotations

from src.python.learning.contracts import (
    AttributionReport,
    EpisodeOutcome,
    RootCauseCandidate,
    SignalEpisode,
)


def _top_features(snap: dict[str, float], n: int = 5) -> dict[str, float]:
    items = []
    for k, v in (snap or {}).items():
        try:
            fv = float(v)
            if fv == fv:
                items.append((k, fv))
        except (TypeError, ValueError):
            continue
    items.sort(key=lambda x: abs(x[1]), reverse=True)
    return {k: v for k, v in items[:n]}


def attribute_episode(ep: SignalEpisode) -> AttributionReport:
    """Deterministic attribution from episode facts (no LLM)."""
    causes: list[str] = []
    notes: list[str] = []

    regime = (ep.regime or "unknown").lower()
    r = float(ep.r_multiple or 0.0)
    pnl = float(ep.pnl or 0.0)

    if ep.outcome == EpisodeOutcome.LOSS.value or r < -0.25:
        if "sideways" in regime or "neutral" in regime:
            causes.append(RootCauseCandidate.BAD_REGIME.value)
            notes.append("loss_in_non_trend_regime")
        if abs(ep.score) < 0.05 and ep.confidence < 0.55:
            causes.append(RootCauseCandidate.FALSE_BREAKOUT.value)
            notes.append("weak_score_confidence")
        votes = ep.ensemble_votes or {}
        if len(votes) >= 2:
            signs = [1 if v > 0 else (-1 if v < 0 else 0) for v in votes.values()]
            if 1 in signs and -1 in signs:
                causes.append(RootCauseCandidate.ENSEMBLE_DISAGREE.value)
                notes.append("ensemble_disagreement")
        if ep.exit_reason and "SL" in str(ep.exit_reason).upper():
            causes.append(RootCauseCandidate.TIGHT_STOP.value)
            notes.append(f"exit={ep.exit_reason}")
        if not causes:
            causes.append(RootCauseCandidate.UNKNOWN.value)
    elif ep.outcome == EpisodeOutcome.WIN.value or r > 0.25:
        notes.append("positive_outcome")
        if "bull" in regime or "trend" in regime:
            notes.append("aligned_with_trend_regime")
    else:
        notes.append("flat_or_open")

    contrib = list(ep.ensemble_votes.keys()) if ep.ensemble_votes else [ep.strategy_id]
    if ep.strategy_id not in contrib:
        contrib = [ep.strategy_id] + contrib

    return AttributionReport(
        episode_id=ep.episode_id,
        symbol=ep.symbol,
        outcome=ep.outcome,
        r_multiple=r,
        primary_strategy=ep.strategy_id,
        regime=ep.regime,
        contributing_strategies=contrib,
        feature_highlights=_top_features(ep.feature_snapshot),
        root_cause_candidates=causes or [RootCauseCandidate.NONE.value],
        notes=notes,
        pnl=pnl,
    )


def attribute_batch(episodes: list[SignalEpisode]) -> list[AttributionReport]:
    return [attribute_episode(e) for e in episodes]
