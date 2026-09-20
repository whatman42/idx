"""Strategy × Regime performance matrix — research plane only.

Idempotent: each episode_id is observed at most once.
Never writes production registry. Never places orders.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Optional

from src.python.learning.contracts import SignalEpisode


@dataclass
class RegimeCell:
    strategy_id: str
    regime: str
    n: int = 0
    wins: int = 0
    sum_r: float = 0.0
    sum_pnl: float = 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def expectancy_r(self) -> float:
        return self.sum_r / self.n if self.n else 0.0

    def reliability(self, min_n: int = 5) -> str:
        if self.n < min_n:
            return "INSUFFICIENT_SAMPLE"
        if self.n < min_n * 2 and abs(self.expectancy_r) < 0.05:
            return "UNSTABLE"
        return "RELIABLE_FOR_RESEARCH"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["win_rate"] = self.win_rate
        d["expectancy_r"] = self.expectancy_r
        d["reliability"] = self.reliability()
        return d


@dataclass
class RegimeMatrix:
    cells: dict[tuple[str, str], RegimeCell] = field(default_factory=dict)
    min_n: int = 5
    _seen: set[str] = field(default_factory=set)

    def observe(self, ep: SignalEpisode) -> bool:
        """Observe once per episode_id. Returns True if newly counted."""
        if ep.outcome in ("OPEN", "SKIPPED"):
            return False
        eid = ep.episode_id or ep.idempotency_key
        if not eid:
            return False
        if eid in self._seen:
            return False
        self._seen.add(eid)
        key = (ep.strategy_id, (ep.regime or "unknown").lower())
        cell = self.cells.get(key)
        if cell is None:
            cell = RegimeCell(strategy_id=key[0], regime=key[1])
            self.cells[key] = cell
        cell.n += 1
        r = float(ep.r_multiple or 0.0)
        cell.sum_r += r
        cell.sum_pnl += float(ep.pnl or 0.0)
        if r > 0:
            cell.wins += 1
        return True

    def observe_many(self, episodes: Iterable[SignalEpisode]) -> int:
        return sum(1 for ep in episodes if self.observe(ep))

    def rebuild(self, episodes: Iterable[SignalEpisode]) -> None:
        """Deterministic rebuild from full episode set (preferred for SSOT)."""
        self.cells.clear()
        self._seen.clear()
        self.observe_many(episodes)

    def reliable_cells(self) -> list[RegimeCell]:
        return [c for c in self.cells.values() if c.n >= self.min_n]

    def weak_pairs(self, *, max_expectancy: float = 0.0, min_n: Optional[int] = None) -> list[RegimeCell]:
        thr = min_n if min_n is not None else self.min_n
        return [
            c for c in self.cells.values()
            if c.n >= thr and c.expectancy_r <= max_expectancy
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cells": [c.to_dict() for c in sorted(self.cells.values(), key=lambda x: (x.strategy_id, x.regime))],
            "min_n": self.min_n,
            "n_cells": len(self.cells),
            "n_seen_episodes": len(self._seen),
        }
