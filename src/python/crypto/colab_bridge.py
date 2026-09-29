"""Crypto Colab research bridge — compute only.

Pipeline: OHLCV → backtest/WFA evaluator → EvidencePackage → CryptoPromotionGate
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from src.python.crypto.evaluator import (
    CryptoEvaluatorConfig,
    backtest_crypto,
    build_evidence_package,
    walk_forward_crypto,
)
from src.python.crypto.promotion_gate import CryptoPromotionGate


@dataclass
class CryptoColabJobResult:
    ok: bool
    job_id: str
    strategy_id: str = ""
    strategy_version: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    promotion: dict[str, Any] = field(default_factory=dict)
    backtest: dict[str, Any] = field(default_factory=dict)
    walk_forward: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    live_execution: bool = False
    orders_submitted: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "job_id": self.job_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "evidence": self.evidence,
            "promotion": self.promotion,
            "backtest_summary": {
                k: self.backtest.get(k)
                for k in ("n_trades", "expectancy", "max_drawdown", "total_pnl")
            },
            "walk_forward_summary": {
                k: self.walk_forward.get(k)
                for k in ("n_windows", "n_trades", "expectancy", "max_drawdown")
            },
            "notes": list(self.notes),
            "live_execution": False,
            "orders_submitted": 0,
            "domain": "CRYPTO",
            "authority": "RESEARCH_ONLY",
        }


def run_crypto_research_pipeline(
    *,
    job_id: str,
    bars: pd.DataFrame,
    strategy_id: str = "crypto_rule_sma20",
    strategy_version: str = "crypto_sma_v0",
    cfg: Optional[CryptoEvaluatorConfig] = None,
    run_gate: bool = True,
    promote_to_paper_allowed: bool = False,
    status_path: Optional[str] = None,
) -> CryptoColabJobResult:
    notes = [
        "CRYPTO_RESEARCH_PIPELINE",
        "no_live_execution",
        "no_order_submission",
        "ledger_ops_not_mutated",
    ]
    bt = backtest_crypto(bars, cfg=cfg)
    wf = walk_forward_crypto(bars, cfg=cfg)
    evidence = build_evidence_package(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        backtest=bt,
        walk_forward=wf,
    )
    promotion: dict[str, Any] = {}
    if run_gate:
        gate = CryptoPromotionGate()
        ev_for_gate = dict(evidence)
        if int(wf.get("n_trades") or 0) > int(evidence.get("n_trades") or 0):
            ev_for_gate["n_trades"] = wf["n_trades"]
            ev_for_gate["expectancy"] = wf.get("expectancy", evidence.get("expectancy"))
            ev_for_gate["max_drawdown"] = max(
                float(evidence.get("max_drawdown") or 0),
                float(wf.get("max_drawdown") or 0),
            )
        dec = gate.evaluate(
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            evidence=ev_for_gate,
            promote_to_paper_allowed=promote_to_paper_allowed,
            persist=True,
            status_path=status_path,
        )
        promotion = dec.to_dict()
        notes.append(f"gate_status={dec.lifecycle_status}")
    return CryptoColabJobResult(
        ok=True,
        job_id=job_id,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        evidence=evidence,
        promotion=promotion,
        backtest=bt,
        walk_forward=wf,
        notes=notes,
    )


def run_crypto_colab_research_stub(
    *,
    job_id: str,
    strategy_id: str = "crypto_rule_sma20",
    strategy_version: str = "crypto_sma_v0",
    bars_meta: Optional[dict[str, Any]] = None,
) -> CryptoColabJobResult:
    empty = pd.DataFrame(columns=["timestamp", "symbol", "open", "high", "low", "close"])
    res = run_crypto_research_pipeline(
        job_id=job_id,
        bars=empty,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        run_gate=True,
    )
    res.notes.append("STUB_NO_BARS")
    if bars_meta:
        res.notes.append(f"bars_meta_keys={list(bars_meta.keys())}")
    return res


def colab_cannot_enable_live() -> bool:
    return True


def colab_cannot_submit_orders() -> bool:
    return True
