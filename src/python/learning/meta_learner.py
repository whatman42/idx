"""Meta-Learner — reliability / uncertainty over strategy outputs (not BUY %)."""
from __future__ import annotations

from collections import defaultdict

from src.python.learning.contracts import MetaDecision, SignalEpisode


class MetaLearner:
    """Learns per-strategy reliability by regime from closed episodes.

    Output is advisory for Governor; never writes production strategy status.
    """

    def __init__(self):
        self._history: dict[tuple[str, str], list[float]] = defaultdict(list)

    def observe(self, ep: SignalEpisode) -> None:
        if ep.outcome in ("OPEN", "SKIPPED"):
            return
        key = (ep.strategy_id, (ep.regime or "unknown").lower())
        self._history[key].append(float(ep.r_multiple or 0.0))

    def reliability(self, strategy_id: str, regime: str) -> float:
        rows = self._history.get((strategy_id, regime.lower()), [])
        if len(rows) < 5:
            return 0.5
        wins = sum(1 for r in rows if r > 0)
        return wins / len(rows)

    def expected_edge(self, strategy_id: str, regime: str) -> float:
        rows = self._history.get((strategy_id, regime.lower()), [])
        if not rows:
            return 0.0
        return sum(rows) / len(rows)

    def uncertainty(self, strategy_id: str, regime: str) -> float:
        rows = self._history.get((strategy_id, regime.lower()), [])
        if len(rows) < 5:
            return 1.0
        mean = sum(rows) / len(rows)
        var = sum((r - mean) ** 2 for r in rows) / len(rows)
        return min(1.0, var ** 0.5)

    def decide(
        self,
        *,
        symbol: str,
        strategy_scores: dict[str, float],
        regime: str,
    ) -> MetaDecision:
        regime_l = (regime or "unknown").lower()
        reliab: dict[str, float] = {}
        edges: dict[str, float] = {}
        uncerts: list[float] = []
        for sid, score in strategy_scores.items():
            reliab[sid] = self.reliability(sid, regime_l)
            edges[sid] = self.expected_edge(sid, regime_l)
            uncerts.append(self.uncertainty(sid, regime_l))

        expected = 0.0
        weight = 0.0
        for sid, score in strategy_scores.items():
            w = max(0.05, reliab.get(sid, 0.5))
            expected += w * float(score) * max(-1.0, min(1.0, edges.get(sid, 0.0) * 5.0 + 0.1))
            weight += w
        expected = expected / weight if weight else 0.0
        unc = sum(uncerts) / len(uncerts) if uncerts else 1.0

        avg_rel = sum(reliab.values()) / len(reliab) if reliab else 0.5
        quality = max(0.0, min(1.0, avg_rel * (1.0 - 0.5 * unc)))

        reasons: list[str] = []
        if unc > 0.7:
            reasons.append("high_uncertainty")
        if avg_rel < 0.45:
            reasons.append("low_strategy_reliability")
        if abs(expected) < 0.02:
            reasons.append("edge_near_zero")

        if quality < 0.35 or unc > 0.85:
            action = "NO_SIGNAL"
        elif expected > 0.05 and quality >= 0.45:
            action = "BUY"
        else:
            action = "HOLD"

        return MetaDecision(
            symbol=symbol,
            expected_edge=float(expected),
            uncertainty=float(unc),
            strategy_reliability=reliab,
            regime_compatibility=float(avg_rel),
            decision_quality=float(quality),
            recommended_action=action,
            reasons=reasons or ["ok"],
        )
