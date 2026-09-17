"""Cost models — simulation assumption vs IDX broker structure.

Paper portfolio MUST use SimulationCostModel (explicit assumptions).
IDXBrokerCostModel is a structural adapter for future calibration from
actual fee/spread/slippage observations — NOT verified fact until calibrated.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass
class CostModel:
    """Backward-compatible default = simulation assumptions."""
    fee_bps: float = 15.0
    slippage_bps: float = 5.0
    status: str = "UNVERIFIED_ASSUMPTION"
    model_kind: str = "SIMULATION"

    def buy_price(self, px: float) -> float:
        return float(px) * (1.0 + self.slippage_bps / 10000.0)

    def sell_price(self, px: float) -> float:
        return float(px) * (1.0 - self.slippage_bps / 10000.0)

    def fee(self, notional: float) -> float:
        return abs(float(notional)) * (self.fee_bps / 10000.0)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SimulationCostModel(CostModel):
    """Paper / research simulation — NOT broker fact."""
    fee_bps: float = 15.0
    exit_fee_bps: float = 25.0
    slippage_bps: float = 5.0
    status: str = "SIMULATION_ASSUMPTION"
    model_kind: str = "SIMULATION"
    note: str = "Fee/slippage are simulation assumptions, not IDX broker schedule."

    def exit_fee(self, notional: float) -> float:
        return abs(float(notional)) * (self.exit_fee_bps / 10000.0)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["buy_fee_bps"] = self.fee_bps
        d["exit_fee_bps"] = self.exit_fee_bps
        return d


@dataclass
class IDXBrokerCostModel(CostModel):
    """Structural IDX equity cost adapter (illustrative schedule).

    status remains UNVERIFIED until calibrated against actual broker invoices.
    Typical IDX retail components (illustrative, not a quote):
      - brokerage commission
      - exchange / clearing fees
      - VAT on commission
      - sell-side levy (e.g. sales tax)
    Use for sensitivity / future calibration only — paper path stays Simulation.
    """
    fee_bps: float = 18.0
    exit_fee_bps: float = 28.0
    slippage_bps: float = 8.0
    status: str = "UNVERIFIED_BROKER_STRUCTURE"
    model_kind: str = "IDX_BROKER"
    note: str = (
        "Illustrative IDX broker cost structure — NOT calibrated. "
        "Do not treat as actual fee schedule until evidence from fills."
    )
    calibrated: bool = False
    source: str = "structure_placeholder"

    def exit_fee(self, notional: float) -> float:
        return abs(float(notional)) * (self.exit_fee_bps / 10000.0)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["buy_fee_bps"] = self.fee_bps
        d["exit_fee_bps"] = self.exit_fee_bps
        return d


def default_paper_cost() -> SimulationCostModel:
    return SimulationCostModel()


def default_broker_cost() -> IDXBrokerCostModel:
    return IDXBrokerCostModel()


def cost_models_summary() -> dict[str, Any]:
    sim = default_paper_cost()
    brk = default_broker_cost()
    return {
        "paper_path": sim.to_dict(),
        "broker_adapter": brk.to_dict(),
        "rule": "paper_uses_simulation_only; broker_adapter_for_calibration",
        "version": "cost_model_v2",
    }
