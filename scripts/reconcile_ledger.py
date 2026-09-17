#!/usr/bin/env python3
"""Rebuild paper portfolio state from trades[] ledger (SSOT).

Usage:
  python -m scripts.reconcile_ledger --path state/paper_portfolio.json --dry-run
  python -m scripts.reconcile_ledger --path state/paper_portfolio.json --apply

Idempotent: rebuild is deterministic from the same trades list.
Does NOT touch ML models, calibration, or production pointers.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.python.ops.paper_portfolio import (
    DEFAULT_INITIAL_CAPITAL,
    PaperPortfolioStore,
    PaperPortfolioState,
    rebuild_portfolio_from_trades,
    validate_portfolio_accounting,
)


def _pos_summary(st: PaperPortfolioState) -> dict[str, Any]:
    open_pos = st.open_positions()
    return {
        "cash": round(float(st.cash), 2),
        "n_open": len(open_pos),
        "positions": {
            sym: {
                "qty": float(p.qty),
                "lots": float(p.lots()),
                "avg_entry": round(float(p.avg_entry), 4),
                "entry_timestamp": p.entry_timestamp,
            }
            for sym, p in open_pos.items()
        },
        "trade_count": int(st.trade_count),
        "n_trades_ledger": len(st.trades or []),
        "realized_pnl": round(float(st.realized_pnl), 2),
    }


def _dedupe_trades_by_order_id(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep first occurrence of each order_id / trade_id (idempotent replay)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for tr in trades or []:
        key = str(tr.get("order_id") or tr.get("trade_id") or "")
        if not key:
            # fallback: signal_id + action + timestamp + symbol
            key = "|".join([
                str(tr.get("signal_id") or ""),
                str(tr.get("action") or tr.get("side") or ""),
                str(tr.get("timestamp") or ""),
                str(tr.get("symbol") or ""),
            ])
        if key in seen:
            continue
        seen.add(key)
        out.append(tr)
    return out


def reconcile(
    path: Path,
    *,
    dry_run: bool = True,
    initial_capital: Optional[float] = None,
) -> dict[str, Any]:
    store = PaperPortfolioStore(path)
    if not store.exists():
        return {"status": "MISSING", "path": str(path), "error": "file_not_found"}

    current = store.load()
    trades = list(current.trades or [])
    trades_deduped = _dedupe_trades_by_order_id(trades)
    cap = float(initial_capital if initial_capital is not None else current.initial_capital or DEFAULT_INITIAL_CAPITAL)

    rebuilt = rebuild_portfolio_from_trades(
        trades_deduped,
        initial_capital=cap,
        simulation_session_id=current.simulation_session_id,
    )
    # Preserve session metadata + ledgers from rebuild path
    rebuilt.trades = trades_deduped
    rebuilt.signal_ledger = list(current.signal_ledger or [])
    rebuilt.applied_order_ids = list(current.applied_order_ids or [])
    rebuilt.model_version = current.model_version
    rebuilt.last_processed_trading_day = current.last_processed_trading_day

    marks = {
        sym: float(p.last_mark or p.avg_entry)
        for sym, p in rebuilt.open_positions().items()
    }
    inv_errs = validate_portfolio_accounting(rebuilt, marks)

    before = _pos_summary(current)
    after = _pos_summary(rebuilt)
    delta_cash = after["cash"] - before["cash"]
    changed = (
        abs(delta_cash) > 0.5
        or before["n_open"] != after["n_open"]
        or before["positions"] != after["positions"]
    )

    report: dict[str, Any] = {
        "status": "DRY_RUN" if dry_run else ("APPLIED" if changed else "NO_CHANGE"),
        "path": str(path),
        "dry_run": dry_run,
        "trades_raw": len(trades),
        "trades_deduped": len(trades_deduped),
        "duplicates_removed": len(trades) - len(trades_deduped),
        "before": before,
        "after": after,
        "delta_cash": round(delta_cash, 2),
        "changed": changed,
        "invariant_ok": len(inv_errs) == 0,
        "invariant_errors": inv_errs,
        "note": "trades[] is SSOT; positions/cash rebuilt deterministically",
    }

    if not dry_run and changed:
        # Archive then write rebuilt
        store.archive_and_reset  # noqa: keep reference for docs
        archive_dir = path.parent / "sessions"
        archive_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime, timezone
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_path = archive_dir / f"pre_reconcile_{stamp}_{path.name}"
        archive_path.write_text(path.read_text())
        report["archive"] = str(archive_path)
        store.save_atomic(rebuilt)
        report["status"] = "APPLIED"

    return report


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Reconcile paper portfolio from trades[] SSOT")
    ap.add_argument("--path", type=Path, default=Path("state/paper_portfolio.json"))
    ap.add_argument("--dry-run", action="store_true", default=True, help="Report only (default)")
    ap.add_argument("--apply", action="store_true", help="Write rebuilt state (archives previous)")
    ap.add_argument("--initial-capital", type=float, default=None)
    args = ap.parse_args(argv)
    dry = not args.apply
    report = reconcile(args.path, dry_run=dry, initial_capital=args.initial_capital)
    print(json.dumps(report, indent=2, default=str))
    if report.get("status") == "MISSING":
        return 2
    if report.get("invariant_ok") is False:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
