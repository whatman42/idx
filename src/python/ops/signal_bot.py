"""IDX operational signal bot — SIGNAL ONLY + continuous paper portfolio (Rp10M).
Default scan: FULL IDX universe (symbols=ALL).
Telegram: deterministic dashboard + optional Gemini executive summary (interpretation only).
"""
from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo
import pandas as pd
import typer
from src.python.data.costs import CostModel
from src.python.data.quality import validate_ohlcv
from src.python.market.providers import SyntheticProvider
from src.python.market.calendar import is_trading_day
from src.python.market.universe import resolve_symbols, universe_meta
from src.python.notify.telegram import TelegramProvider
from src.python.ops.notify_state import NotifyStateStore
from src.python.ops.telegram_format import notification_id
from src.python.ops.freshness import freshness_gate
from src.python.ops.paper_portfolio import (
    DEFAULT_INITIAL_CAPITAL, DEFAULT_LOT_SIZE, PaperPortfolioStore, apply_long_entry,
    mark_to_market, new_session, summary as portfolio_summary, paper_reset_scope,
    process_tp_sl_exits, compute_tp_sl,
)
from src.python.ops.risk_gate import gate_new_entry, risk_defaults, estimate_open_heat
from src.python.ops.production_signal import production_signals_from_bars
from src.python.data.costs import SimulationCostModel, cost_models_summary
from src.python.validation.economic_sim import simulate_long_only
from src.python.ops.readiness import assess_readiness
from src.python.llm.gemini_narrator import narrate_halt
from src.python.llm.executive_summary_gemini import generate_executive_summary
from src.python.reporting.builder import build_buy_signal, build_cycle_report
from src.python.reporting.finance import shares_from_lots, lots_from_shares, SHARES_PER_LOT
from src.python.reporting.llm_boundary import compose_with_executive_summary
from src.python.reporting.executive_summary import (
    build_executive_payload, payload_fingerprint, should_emit_summary, mark_emitted,
)
from src.python.reporting.composer import compose_telegram_message
from src.python.reporting.validation import validate_cycle_report

def _research_ingest_paper_trades(pf, state_path: Path, report: dict) -> None:
    """POST-FILL research-only observer. Fail-safe: never affects paper/ledger/execution."""
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

def _telegram_text_from_cycle(cycle, report: dict) -> tuple:
    """Deterministic dashboard + optional Gemini executive summary (reporting only)."""
    payload = build_executive_payload(cycle)
    fp = payload_fingerprint(payload)
    exec_text, obs = generate_executive_summary(payload, use_llm=True)
    obs_d = obs.to_dict()
    obs_d["input_fingerprint"] = fp
    if not should_emit_summary(fp, channel="telegram_exec"):
        text = compose_telegram_message(cycle)
        obs_d["duplicate_suppressed"] = True
        return text, "deterministic", obs_d
    text, src = compose_with_executive_summary(cycle, executive_text=exec_text, executive_enabled=True)
    mark_emitted(fp, channel="telegram_exec")
    return text, src, obs_d

app = typer.Typer(add_completion=False)
JKT = ZoneInfo("Asia/Jakarta")
VALID_MODES = {"TEST", "PAPER", "OPERATIONAL"}
TOP_N_SIGNAL = 3  # rank top-N; risk_gate decides how many actually fill
ENTRY_WEIGHT = 0.05  # fallback only if risk_gate unavailable

# NOTE: remainder of file restored from local verified Phase-1 implementation
# Full file content continues in follow-up if truncated
