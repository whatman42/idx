from __future__ import annotations
from dataclasses import dataclass
from typing import Sequence
import numpy as np
import pandas as pd

@dataclass
class DataContract:
    df: pd.DataFrame
    source: str

class SyntheticProvider:
    def __init__(self, n: int = 80, seed: int = 42):
        self.n = n
        self.seed = seed

    def fetch(self, symbols: Sequence[str]) -> DataContract:
        rng = np.random.default_rng(self.seed)
        rows = []
        idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=self.n)
        for i, sym in enumerate(symbols):
            px = 1000 + i * 500 + np.cumsum(rng.normal(0, 5, len(idx)))
            px = np.maximum(px, 100)
            for t, p in zip(idx, px):
                rows.append({
                    "timestamp": t, "symbol": sym,
                    "open": float(p), "high": float(p * 1.01), "low": float(p * 0.99),
                    "close": float(p), "volume": float(1e6),
                })
        return DataContract(pd.DataFrame(rows), source="synthetic")
