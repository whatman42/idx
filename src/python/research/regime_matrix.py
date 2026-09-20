"""Strategy × Regime performance matrix — research plane only.

Answers: for each strategy, expectancy / win-rate / n by regime.
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

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["win_rate"] = self.win_rate
        d["expectancy_r"] = self.expectancy_r
        return d


@dataclass
class RegimeMatrix:
    cells: dict[tuple[str, str], RegimeCell] = field(default_factory=dict)
    min_n: int = 5

    def observe(self, ep: SignalEpisode) -> None:
        if ep.outcome in ("OPEN", "SKIPPED"):
            return
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

    def observe_many(self, episodes: Iterable[SignalEpisode]) -> None:
        for ep in episodes:
            self.observe(ep)

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
        }
