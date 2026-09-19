"""Research-only post-fill learning observer. Fail-safe; never affects paper/ledger."""
from __future__ import annotations
from pathlib import Path
from typing import Any

def research_ingest_paper_trades(pf: Any, state_path: Path, report: dict) -> None:
    try:
        from src.python.learning.loop import LearningLoop
        trades = list(getattr(pf, "trades", None) or [])
        if not trades:
            report["learning_ingest"] = {"status": "NO_TRADES", "principle": "research_only_no_execution"}
            return
        learn_dir = Path(state_path) / "learning"
        learn_dir.mkdir(parents=True, exist_ok=True)
        loop = LearningLoop(state_dir=learn_dir)
        result = loop.ingest_from_paper_trades(
            trades,
            strategy_id="rule_sma20",
            session_id=str(getattr(pf, "simulation_session_id", "") or ""),
            ledger_realized_pnl=float(getattr(pf, "realized_pnl", 0) or 0),
        )
        report["learning_ingest"] = {
            "status": "OK" if (result.get("gate") or {}).get("learning_update") == "ALLOW" else "BLOCKED_OR_PARTIAL",
            "ingest": result.get("ingest"),
            "gate": result.get("gate"),
            "integrity_ok": (result.get("integrity") or {}).get("ok"),
            "principle": "research_only_no_execution",
        }
    except Exception as e:
        report["learning_ingest"] = {
            "status": "FAILED_ISOLATED",
            "error": type(e).__name__,
            "detail": str(e)[:200],
            "principle": "research_only_no_execution_fail_safe",
        }
