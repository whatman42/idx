"""Crypto Operational Awareness Layer — read-only, deterministic, auditable.

NOT consciousness. NOT a decision-maker. NOT allowed to mutate:
  strategy, risk config, promotion state, execution policy, paper ledger.

Produces cycle diagnosis answering:
  WHAT DID I SEE / DECIDE / REFUSE / EXECUTE / WHY /
  FINANCIAL STATE / SYSTEM HEALTH / WHAT CHANGED
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

AWARENESS_VERSION = "crypto_awareness_v1"
PREV_SNAPSHOT_PATH = "artifacts/crypto/awareness/last_cycle_snapshot.json"


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class CycleAwarenessReport:
    awareness_version: str = AWARENESS_VERSION
    cycle_id: str = ""
    generated_at: str = ""
    live_execution: bool = False
    paper_only: bool = True
    read_only: bool = True
    can_mutate_strategy: bool = False
    can_mutate_risk: bool = False
    can_mutate_promotion: bool = False
    can_mutate_execution_policy: bool = False
    can_mutate_ledger: bool = False

    what_i_saw: dict[str, Any] = field(default_factory=dict)
    what_i_decided: dict[str, Any] = field(default_factory=dict)
    what_i_refused: dict[str, Any] = field(default_factory=dict)
    what_i_executed: dict[str, Any] = field(default_factory=dict)
    why: list[str] = field(default_factory=list)
    financial_state: dict[str, Any] = field(default_factory=dict)
    system_health: str = "UNKNOWN"
    health_reasons: list[str] = field(default_factory=list)
    what_changed: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _classify_health(report: dict[str, Any]) -> tuple[str, list[str]]:
    reasons: list[str] = []
    status = str(report.get("status") or "")
    if status in ("FAIL_CLOSED_PROVIDER", "BLOCKED_STRATEGY_STATUS", "DISABLED"):
        reasons.append(f"STATUS:{status}")
        return "BLOCKED", reasons

    dq = int(report.get("data_quality_blocks") or report.get("data_quality_block_count") or 0)
    risk = int(report.get("risk_blocks") or report.get("risk_skips") or 0)
    gov = int(report.get("governor_blocks") or 0)
    gate = int(report.get("gate_blocks") or 0)
    ohlcv_err = int(report.get("ohlcv_error_count") or 0)

    if ohlcv_err > 0 and int(report.get("ohlcv_ok") or 0) == 0:
        reasons.append("NO_OHLCV_OK")
        return "BLOCKED", reasons

    degraded = False
    if dq > 0:
        reasons.append(f"DATA_QUALITY_BLOCKS:{dq}")
        degraded = True
    if risk > 0:
        reasons.append(f"RISK_BLOCKS:{risk}")
        degraded = True
    if gov > 0:
        reasons.append(f"GOVERNOR_BLOCKS:{gov}")
        degraded = True
    if gate > 0:
        reasons.append(f"GATE_BLOCKS:{gate}")
        degraded = True
    if ohlcv_err > 0:
        reasons.append(f"OHLCV_ERRORS:{ohlcv_err}")
        degraded = True
    if degraded:
        return "DEGRADED", reasons
    reasons.append("ALL_GATES_NOMINAL")
    return "HEALTHY", reasons


def _load_prev(path: str = PREV_SNAPSHOT_PATH) -> Optional[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_snapshot(snapshot: dict[str, Any], path: str = PREV_SNAPSHOT_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(snapshot, indent=2, default=str), encoding="utf-8")


def _diff_changed(prev: Optional[dict[str, Any]], cur: dict[str, Any]) -> dict[str, Any]:
    if not prev:
        return {"baseline": "FIRST_CYCLE", "deltas": {}}
    keys = (
        "fills_paper",
        "signals_count",
        "data_quality_blocks",
        "risk_blocks",
        "governor_blocks",
        "gate_blocks",
        "equity",
        "cash",
        "positions_count",
        "system_health",
    )
    deltas: dict[str, Any] = {}
    for k in keys:
        a, b = prev.get(k), cur.get(k)
        if a != b:
            deltas[k] = {"from": a, "to": b}
    return {
        "prev_cycle_id": prev.get("cycle_id"),
        "deltas": deltas,
        "unchanged": [k for k in keys if k not in deltas],
    }


def build_cycle_awareness(
    ops_report: dict[str, Any],
    *,
    prev_snapshot_path: str = PREV_SNAPSHOT_PATH,
    persist_snapshot: bool = True,
) -> dict[str, Any]:
    """Read-only diagnosis from an ops cycle report. Never mutates ledger/strategy."""
    uni = ops_report.get("universe") or {}
    pf = ops_report.get("portfolio") or {}
    cov = (ops_report.get("coverage") or {}).get("coverage") or ops_report.get("coverage") or {}

    health, health_reasons = _classify_health(ops_report)

    why: list[str] = []
    if ops_report.get("strategy_status_reason"):
        why.append(f"STRATEGY_STATUS:{ops_report['strategy_status_reason']}")
    if int(ops_report.get("data_quality_blocks") or 0):
        why.append("DATA_QUALITY_BLOCK")
    if int(ops_report.get("risk_blocks") or ops_report.get("risk_skips") or 0):
        why.append("RISK_BLOCK")
    if int(ops_report.get("governor_blocks") or 0):
        why.append("GOVERNOR_BLOCK")
    if int(ops_report.get("gate_blocks") or 0):
        why.append("EXECUTION_GATE_BLOCK")
    if int(ops_report.get("blocked_no_next_count") or 0):
        why.append("NO_FILL_MISSING_T+1")
    if int(ops_report.get("fills_paper") or 0):
        why.append("PAPER_FILL_APPLIED")
    if not why:
        why.append("NOMINAL_OR_NO_ACTION")

    positions = pf.get("positions") or {}
    cur_snap = {
        "cycle_id": ops_report.get("cycle_id"),
        "fills_paper": int(ops_report.get("fills_paper") or 0),
        "signals_count": int(ops_report.get("signals_count") or 0),
        "data_quality_blocks": int(
            ops_report.get("data_quality_blocks") or ops_report.get("data_quality_block_count") or 0
        ),
        "risk_blocks": int(ops_report.get("risk_blocks") or ops_report.get("risk_skips") or 0),
        "governor_blocks": int(ops_report.get("governor_blocks") or 0),
        "gate_blocks": int(ops_report.get("gate_blocks") or 0),
        "equity": pf.get("equity"),
        "cash": pf.get("cash"),
        "positions_count": len(positions),
        "system_health": health,
        "generated_at": _utc(),
    }
    prev = _load_prev(prev_snapshot_path)
    changed = _diff_changed(prev, cur_snap)

    rep = CycleAwarenessReport(
        cycle_id=str(ops_report.get("cycle_id") or ""),
        generated_at=_utc(),
        what_i_saw={
            "universe_eligible": uni.get("eligible_count") or cov.get("eligible"),
            "universe_discovered": uni.get("discovered_count") or cov.get("discovered"),
            "ohlcv_ok": ops_report.get("ohlcv_ok"),
            "ohlcv_attempted": ops_report.get("ohlcv_attempted"),
            "ohlcv_error_count": ops_report.get("ohlcv_error_count"),
            "signal_coverage": ops_report.get("signal_coverage"),
            "signal_coverage_mode": ops_report.get("signal_coverage_mode"),
            "endpoint_used": ops_report.get("endpoint_used"),
            "execution_policy": ops_report.get("execution_policy"),
            "strategy_id": ops_report.get("strategy_id"),
            "strategy_version": ops_report.get("strategy_version"),
        },
        what_i_decided={
            "signals_count": ops_report.get("signals_count"),
            "intents_count": ops_report.get("intents_count"),
            "signal_contracts_count": ops_report.get("signal_contracts_count"),
            "strategy_status_reason": ops_report.get("strategy_status_reason"),
        },
        what_i_refused={
            "data_quality_blocks": cur_snap["data_quality_blocks"],
            "risk_blocks": cur_snap["risk_blocks"],
            "governor_blocks": cur_snap["governor_blocks"],
            "gate_blocks": cur_snap["gate_blocks"],
            "blocked_no_next_count": ops_report.get("blocked_no_next_count"),
            "ohlcv_errors_sample": (ops_report.get("ohlcv_errors") or [])[:20],
        },
        what_i_executed={
            "fills_paper": cur_snap["fills_paper"],
            "execution_policy": ops_report.get("execution_policy"),
            "same_bar_fill": False,
            "paper_only": True,
            "broker": "NOT_SENT_NO_LIVE_EXECUTION",
        },
        why=why,
        financial_state={
            "base_currency": ops_report.get("base_currency") or "USDT",
            "cash": pf.get("cash"),
            "market_value": pf.get("market_value"),
            "equity": pf.get("equity"),
            "realized_pnl": pf.get("realized_pnl"),
            "fees_paid": pf.get("fees_paid"),
            "positions_count": len(positions),
            "position_symbols": sorted(list(positions.keys()))[:30],
        },
        system_health=health,
        health_reasons=health_reasons,
        what_changed=changed,
    )
    out = rep.to_dict()
    if persist_snapshot:
        _save_snapshot(cur_snap, prev_snapshot_path)
        art = Path("artifacts/crypto/awareness")
        art.mkdir(parents=True, exist_ok=True)
        (art / "last_awareness.json").write_text(
            json.dumps(out, indent=2, default=str), encoding="utf-8"
        )
        cid = str(ops_report.get("cycle_id") or "unknown").replace("/", "_")
        (art / f"awareness_{cid}.json").write_text(
            json.dumps(out, indent=2, default=str), encoding="utf-8"
        )
    return out
