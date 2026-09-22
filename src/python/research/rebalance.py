"""Portfolio rebalance — RESEARCH / SHADOW plane only.

Equal-weight + relative drift threshold + TRIM_ONLY candidates.
Does NOT execute, does NOT call apply_exit / paper fill / broker.

Authority model (unchanged):
  Signal → Risk → Governor → Market Structure Gate → Paper Execution → Ledger

Any future trim execution MUST enter that path; this module only proposes plans.

Invariants:
  LIVE_EXECUTION = FALSE
  rebalance order != broker order
  Ledger = SSOT (when execution is later enabled)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Optional, Sequence


DEFAULT_RELATIVE_DRIFT_THRESHOLD = 0.20  # 20%
MIN_OPEN_FOR_REBALANCE = 2
PLANE = "RESEARCH_SHADOW"
ACTION_POLICY = "TRIM_ONLY"


class RebalanceActionKind(str, Enum):
    NO_ACTION = "NO_ACTION"
    TRIM_CANDIDATE = "TRIM_CANDIDATE"
    TOP_UP_FORBIDDEN = "TOP_UP_FORBIDDEN"


@dataclass(frozen=True)
class PositionWeightView:
    symbol: str
    market_value: float
    actual_weight: float
    target_weight: float
    drift: float
    relative_drift: float


@dataclass(frozen=True)
class RebalanceLeg:
    symbol: str
    kind: RebalanceActionKind
    actual_weight: float
    target_weight: float
    relative_drift: float
    suggested_trim_weight: float = 0.0
    detail: str = ""


@dataclass(frozen=True)
class RebalancePlan:
    """Immutable research object — not an order, not executable by itself."""

    equity: float
    n_open: int
    threshold: float
    policy: str = ACTION_POLICY
    plane: str = PLANE
    live_execution: bool = False
    broker_execution: bool = False
    legs: tuple[RebalanceLeg, ...] = ()
    weights: tuple[PositionWeightView, ...] = ()
    trigger_count: int = 0
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "equity": self.equity,
            "n_open": self.n_open,
            "threshold": self.threshold,
            "policy": self.policy,
            "plane": self.plane,
            "live_execution": self.live_execution,
            "broker_execution": self.broker_execution,
            "trigger_count": self.trigger_count,
            "notes": list(self.notes),
            "weights": [asdict(w) for w in self.weights],
            "legs": [
                {
                    **{k: (v.value if isinstance(v, Enum) else v) for k, v in asdict(leg).items()},
                }
                for leg in self.legs
            ],
            "execution_authority": "NONE_RESEARCH_ONLY",
            "requires_for_future_exec": [
                "risk_gate",
                "governor",
                "market_structure_gate",
                "paper_path_only",
            ],
        }


def calculate_target_weights(
    symbols: Sequence[str],
    *,
    scheme: str = "equal_weight",
) -> dict[str, float]:
    """target_weight_i = 1 / N_open for equal_weight."""
    syms = [str(s).upper() for s in symbols if s]
    n = len(syms)
    if n == 0:
        return {}
    if scheme != "equal_weight":
        raise ValueError(f"unsupported_scheme:{scheme}")
    w = 1.0 / n
    return {s: w for s in syms}


def position_weights_from_values(
    market_values: Mapping[str, float],
    equity: float,
) -> dict[str, float]:
    if equity <= 0:
        return {str(s).upper(): 0.0 for s in market_values}
    return {
        str(s).upper(): float(v) / float(equity)
        for s, v in market_values.items()
        if float(v) > 0
    }


def relative_drift(actual: float, target: float) -> float:
    if target <= 1e-15:
        return 0.0 if abs(actual) <= 1e-15 else float("inf")
    return abs(float(actual) - float(target)) / float(target)


def detect_drift(
    actual_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
    *,
    threshold: float = DEFAULT_RELATIVE_DRIFT_THRESHOLD,
) -> list[PositionWeightView]:
    out: list[PositionWeightView] = []
    for sym, tw in target_weights.items():
        aw = float(actual_weights.get(sym, 0.0))
        d = aw - float(tw)
        rd = relative_drift(aw, float(tw))
        out.append(
            PositionWeightView(
                symbol=sym,
                market_value=0.0,
                actual_weight=aw,
                target_weight=float(tw),
                drift=d,
                relative_drift=rd,
            )
        )
    return out


def build_rebalance_plan(
    *,
    market_values: Mapping[str, float],
    equity: float,
    threshold: float = DEFAULT_RELATIVE_DRIFT_THRESHOLD,
    scheme: str = "equal_weight",
) -> RebalancePlan:
    """Equal-weight targets, relative drift trigger, TRIM_ONLY legs. Research only."""
    notes: list[str] = []
    mv = {str(k).upper(): float(v) for k, v in market_values.items() if float(v) > 0}
    n_open = len(mv)

    if equity <= 0:
        notes.append("non_positive_equity")
        return RebalancePlan(
            equity=float(equity), n_open=n_open, threshold=float(threshold), notes=tuple(notes)
        )

    if n_open < MIN_OPEN_FOR_REBALANCE:
        notes.append(f"n_open<{MIN_OPEN_FOR_REBALANCE}_no_rebalance")
        targets = calculate_target_weights(list(mv.keys()), scheme=scheme) if n_open else {}
        actual = position_weights_from_values(mv, equity)
        weights = []
        for sym, tw in targets.items():
            aw = actual.get(sym, 0.0)
            weights.append(
                PositionWeightView(
                    symbol=sym,
                    market_value=mv.get(sym, 0.0),
                    actual_weight=aw,
                    target_weight=tw,
                    drift=aw - tw,
                    relative_drift=relative_drift(aw, tw),
                )
            )
        return RebalancePlan(
            equity=float(equity),
            n_open=n_open,
            threshold=float(threshold),
            weights=tuple(weights),
            notes=tuple(notes),
        )

    targets = calculate_target_weights(list(mv.keys()), scheme=scheme)
    actual = position_weights_from_values(mv, equity)
    weights: list[PositionWeightView] = []
    legs: list[RebalanceLeg] = []
    triggers = 0

    for sym, tw in targets.items():
        aw = actual.get(sym, 0.0)
        rd = relative_drift(aw, tw)
        d = aw - tw
        weights.append(
            PositionWeightView(
                symbol=sym,
                market_value=mv.get(sym, 0.0),
                actual_weight=aw,
                target_weight=tw,
                drift=d,
                relative_drift=rd,
            )
        )
        if rd > float(threshold) and d > 0:
            legs.append(
                RebalanceLeg(
                    symbol=sym,
                    kind=RebalanceActionKind.TRIM_CANDIDATE,
                    actual_weight=aw,
                    target_weight=tw,
                    relative_drift=rd,
                    suggested_trim_weight=max(0.0, d),
                    detail=f"overweight relative_drift={rd:.4f}>{threshold}",
                )
            )
            triggers += 1
        elif rd > float(threshold) and d < 0:
            legs.append(
                RebalanceLeg(
                    symbol=sym,
                    kind=RebalanceActionKind.TOP_UP_FORBIDDEN,
                    actual_weight=aw,
                    target_weight=tw,
                    relative_drift=rd,
                    detail="underweight_requires_signal_and_risk_not_auto_topup",
                )
            )
            notes.append(f"{sym}_underweight_no_auto_buy")
        else:
            legs.append(
                RebalanceLeg(
                    symbol=sym,
                    kind=RebalanceActionKind.NO_ACTION,
                    actual_weight=aw,
                    target_weight=tw,
                    relative_drift=rd,
                    detail="within_threshold",
                )
            )

    if triggers == 0:
        notes.append("no_trim_triggers")
    notes.append("research_shadow_no_execution")
    notes.append("future_trim_must_pass_risk_governor_ms_gate")

    return RebalancePlan(
        equity=float(equity),
        n_open=n_open,
        threshold=float(threshold),
        legs=tuple(legs),
        weights=tuple(weights),
        trigger_count=triggers,
        notes=tuple(notes),
    )


def plan_from_portfolio_snapshot(
    *,
    open_positions: Mapping[str, Mapping[str, Any]],
    equity: float,
    marks: Optional[Mapping[str, float]] = None,
    threshold: float = DEFAULT_RELATIVE_DRIFT_THRESHOLD,
) -> RebalancePlan:
    """Helper from paper-portfolio-like dicts. Research only — never mutates portfolio."""
    marks = marks or {}
    mv: dict[str, float] = {}
    for sym, p in open_positions.items():
        if not isinstance(p, Mapping):
            continue
        qty = float(p.get("qty") or 0)
        if qty <= 0:
            continue
        mark = marks.get(sym)
        if mark is None:
            mark = p.get("last_mark") or p.get("avg_entry") or 0
        val = qty * float(mark)
        if val > 0:
            mv[str(sym).upper()] = val
    return build_rebalance_plan(market_values=mv, equity=float(equity), threshold=threshold)
