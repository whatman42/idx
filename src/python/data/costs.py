from __future__ import annotations
from dataclasses import dataclass

@dataclass
class CostModel:
    fee_bps: float = 15.0
    slippage_bps: float = 5.0
    status: str = "UNVERIFIED_ASSUMPTION"

    def buy_price(self, px: float) -> float:
        return float(px) * (1.0 + self.slippage_bps / 10000.0)

    def sell_price(self, px: float) -> float:
        return float(px) * (1.0 - self.slippage_bps / 10000.0)

    def fee(self, notional: float) -> float:
        return abs(float(notional)) * (self.fee_bps / 10000.0)
