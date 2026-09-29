"""P3+ real historical evidence runner — research plane only.

Order: OHLCV → FeatureSnapshot → SMA20+shadow → WFA → Evidence → Gate → MANUAL_REVIEW
Never auto PAPER_ALLOWED. Never LIVE_EXECUTION. Never mutates paper ledger.

mode=smoke (8×90): pipeline only. mode=full (40×250): minimum for lifecycle review.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Optional, Sequence

import pandas as pd

from src.python.crypto.config import (
    CRYPTO_EXECUTION_POLICY,
    assert_crypto_paper_only,
    crypto_sim_assumptions,
)
from src.python.crypto.evaluator import CryptoEvaluatorConfig, backtest_crypto
from src.python.crypto.feature_snapshot import CRYPTO_FEATURE_SET_VERSION
from src.python.crypto.provider import BinancePublicProvider
from src.python.crypto.shadow_eval import (
    REFERENCE_ID,
    REFERENCE_VERSION,
    SHADOW_ID,
    SHADOW_VERSION,
    _signal_fn_for_scorer,
    run_shadow_comparison,
)
from src.python.crypto.universe import CryptoUniverseProvider

PLANE = "CRYPTO_RESEARCH_EVIDENCE"
SMOKE_MAX_SYMBOLS = 8
SMOKE_OHLCV_LIMIT = 90
FULL_MAX_SYMBOLS = 40
FULL_OHLCV_LIMIT = 250


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_research_bars(
    *,
    symbols: Optional[Sequence[str]] = None,
    max_symbols: int = 12,
    ohlcv_limit: int = 120,
    provider: Optional[BinancePublicProvider] = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    assert_crypto_paper_only()
    prov = provider or BinancePublicProvider()
    meta: dict[str, Any] = {
        "provider": "binance_public",
        "ohlcv_limit": ohlcv_limit,
        "endpoint_used": "",
        "errors": [],
        "symbols_requested": [],
        "symbols_ok": [],
        "bars_per_symbol": {},
    }
    if symbols:
        targets = [str(s) for s in symbols][:max_symbols]
    else:
        uni = CryptoUniverseProvider(prov)
        disc = uni.discover()
        eligible = list(disc.eligible)[:max_symbols]
        targets = [i.symbol for i in eligible]
        meta["universe_eligible_count"] = disc.eligible_count
    meta["symbols_requested"] = list(targets)
    frames: list[pd.DataFrame] = []
    for sym in targets:
        try:
            raw = sym.replace("/", "") if "/" in sym else sym
            bars = prov.fetch_ohlcv(sym, interval="1d", limit=ohlcv_limit, raw_symbol=raw)
            if not bars:
                meta["errors"].append(f"{sym}:EMPTY")
                continue
            frames.append(
                pd.DataFrame(
                    [
                        {
                            "symbol": b.symbol,
                            "timestamp": b.timestamp,
                            "open": b.open,
                            "high": b.high,
                            "low": b.low,
                            "close": b.close,
                            "volume": b.volume,
                        }
                        for b in bars
                    ]
                )
            )
            meta["symbols_ok"].append(sym)
            meta["bars_per_symbol"][sym] = len(bars)
        except Exception as e:
            meta["errors"].append(f"{sym}:{type(e).__name__}")
    meta["endpoint_used"] = getattr(prov, "endpoint_used", "")
    if not frames:
        return pd.DataFrame(), meta
    return pd.concat(frames, ignore_index=True), meta


def _period_meta(df: pd.DataFrame) -> dict[str, Any]:
    if df is None or df.empty or "timestamp" not in df.columns:
        return {"start": None, "end": None, "n_rows": 0}
    ts = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    return {
        "start": str(ts.min()) if len(ts) else None,
        "end": str(ts.max()) if len(ts) else None,
        "n_rows": int(len(df)),
        "n_symbols": int(df["symbol"].nunique()) if "symbol" in df.columns else 0,
    }


def _profit_factor(trades: list[dict]) -> Optional[float]:
    if not trades:
        return None
    gains = sum(float(t.get("pnl") or 0) for t in trades if float(t.get("pnl") or 0) > 0)
    losses = sum(abs(float(t.get("pnl") or 0)) for t in trades if float(t.get("pnl") or 0) < 0)
    if losses <= 0:
        return None if gains <= 0 else float("inf")
    return float(gains / losses)


def _per_symbol_stats(
    bars: pd.DataFrame, strategy_id: str, cfg: CryptoEvaluatorConfig
) -> list[dict[str, Any]]:
    sig_fn = _signal_fn_for_scorer(strategy_id)
    out: list[dict[str, Any]] = []
    if bars is None or bars.empty:
        return out
    for sym, g in bars.groupby("symbol", sort=False):
        res = backtest_crypto(g, cfg=cfg, signal_fn=sig_fn)
        trades = res.get("trades") or []
        out.append(
            {
                "symbol": str(sym),
                "n_bars": int(len(g)),
                "n_trades": int(res.get("n_trades") or 0),
                "expectancy": float(res.get("expectancy") or 0.0),
                "total_pnl": float(res.get("total_pnl") or 0.0),
                "max_drawdown": float(res.get("max_drawdown") or 0.0),
                "win_rate": res.get("win_rate"),
                "profit_factor": _profit_factor(trades),
            }
        )
    return out


def _symbol_consistency(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "n_symbols": 0,
            "symbols_with_trades": 0,
            "positive_expectancy_symbols": 0,
            "positive_symbol_ratio": 0.0,
            "warning": "NO_SYMBOL_BREAKDOWN",
        }
    with_tr = [r for r in rows if int(r.get("n_trades") or 0) > 0]
    pos = [r for r in with_tr if float(r.get("expectancy") or 0) > 0]
    return {
        "n_symbols": len(rows),
        "symbols_with_trades": len(with_tr),
        "positive_expectancy_symbols": len(pos),
        "positive_symbol_ratio": (len(pos) / len(with_tr)) if with_tr else 0.0,
        "worst_symbol_expectancy": float(
            min((r.get("expectancy") or 0 for r in with_tr), default=0.0)
        ),
        "warning": (
            "AGGREGATE_ONLY_UNRELIABLE"
            if with_tr and (len(pos) / len(with_tr)) < 0.5
            else None
        ),
    }


def _strategy_review_block(
    *,
    strategy_id: str,
    strategy_version: str,
    role: str,
    pack: dict[str, Any],
    per_symbol: list[dict[str, Any]],
) -> dict[str, Any]:
    ev = pack.get("evidence") or {}
    gate = pack.get("gate") or {}
    wf = ev.get("walk_forward") or {}
    return {
        "strategy_id": strategy_id,
        "strategy_version": strategy_version,
        "role": role,
        "feature_version": CRYPTO_FEATURE_SET_VERSION,
        "execution_policy": CRYPTO_EXECUTION_POLICY,
        "fee_slippage_model": crypto_sim_assumptions(),
        "n_trades": int(ev.get("n_trades") or 0),
        "expectancy": float(ev.get("expectancy") or 0.0),
        "total_pnl": ev.get("total_pnl"),
        "max_drawdown": float(ev.get("max_drawdown") or 0.0),
        "win_rate": ev.get("win_rate"),
        "hard_rejects": list(ev.get("hard_reject") or []),
        "wfa": {
            "n_windows": wf.get("n_windows", 0),
            "n_trades": wf.get("n_trades", 0),
            "expectancy": wf.get("expectancy"),
            "max_drawdown": wf.get("max_drawdown"),
        },
        "gate_status": gate.get("lifecycle_status"),
        "gate_reasons": list(gate.get("reasons") or []),
        "gate_approved": bool(gate.get("approved")),
        "per_symbol": per_symbol,
        "symbol_consistency": _symbol_consistency(per_symbol),
    }


def build_manual_review_report(
    *,
    comparison: dict[str, Any],
    data_meta: dict[str, Any],
    period: dict[str, Any],
    mode: str,
    ref_symbols: list[dict[str, Any]],
    shadow_symbols: list[dict[str, Any]],
    fold_ref: dict[str, Any],
    fold_shadow: dict[str, Any],
) -> dict[str, Any]:
    ref = comparison.get("reference") or {}
    sh = comparison.get("shadow") or {}
    cmp_ = comparison.get("comparison") or {}
    ref_block = _strategy_review_block(
        strategy_id=REFERENCE_ID,
        strategy_version=REFERENCE_VERSION,
        role="REFERENCE_PAPER_PATH",
        pack=ref,
        per_symbol=ref_symbols,
    )
    ref_block["fold_consistency"] = fold_ref
    sh_block = _strategy_review_block(
        strategy_id=SHADOW_ID,
        strategy_version=SHADOW_VERSION,
        role="SHADOW_RESEARCH_ONLY",
        pack=sh,
        per_symbol=shadow_symbols,
    )
    sh_block["fold_consistency"] = fold_shadow
    sh_block["paper_eligible"] = False
    return {
        "document": "CRYPTO_MANUAL_REVIEW_EVIDENCE",
        "status": "READY_FOR_MANUAL_REVIEW",
        "evidence_status": "GENERATED",
        "promotion_gate_status": {
            "reference": ref_block.get("gate_status"),
            "shadow": sh_block.get("gate_status"),
        },
        "manual_review_required": True,
        "paper_ledger_mutated": False,
        "live_execution": False,
        "auto_paper_allowed": False,
        "mode": mode,
        "mode_note": (
            "SMOKE: pipeline validation only — insufficient for lifecycle decision"
            if mode == "smoke"
            else "FULL: intended minimum dataset for human lifecycle review"
        ),
        "dataset": {
            "period": period,
            "universe_coverage": {
                "eligible_count": data_meta.get("universe_eligible_count"),
                "symbols_requested": data_meta.get("symbols_requested"),
                "symbols_evaluated": data_meta.get("symbols_ok"),
                "bars_per_symbol": data_meta.get("bars_per_symbol"),
                "errors": data_meta.get("errors"),
                "source": data_meta.get("source"),
                "endpoint_used": data_meta.get("endpoint_used"),
            },
        },
        "feature_version": CRYPTO_FEATURE_SET_VERSION,
        "execution_policy": CRYPTO_EXECUTION_POLICY,
        "fee_slippage_model": crypto_sim_assumptions(),
        "strategies": {
            "reference_sma20": ref_block,
            "shadow_momentum": sh_block,
        },
        "sma20_reference_comparison": {
            "delta_expectancy": cmp_.get("delta_expectancy"),
            "shadow_expectancy": cmp_.get("shadow_expectancy"),
            "reference_expectancy": cmp_.get("reference_expectancy"),
            "shadow_n_trades": cmp_.get("shadow_n_trades"),
            "reference_n_trades": cmp_.get("reference_n_trades"),
            "shadow_beats_reference_aggregate": cmp_.get("shadow_beats_reference"),
            "caveat": (
                "Do NOT promote from aggregate delta_expectancy alone. "
                "Require fold consistency and per-symbol distribution."
            ),
        },
        "consistency_warnings": [
            w
            for w in [
                ref_block["symbol_consistency"].get("warning"),
                sh_block["symbol_consistency"].get("warning"),
                (
                    "LOW_FOLD_CONSISTENCY_SHADOW"
                    if (fold_shadow.get("positive_fold_ratio") or 0) < 0.5
                    and (fold_shadow.get("n_folds") or 0) > 0
                    else None
                ),
            ]
            if w
        ],
        "review_checklist": [
            "Verify dataset mode (smoke vs full) and period coverage",
            "Inspect bars_per_symbol and universe coverage",
            "Compare WFA fold expectancy distribution (not only mean)",
            "Compare per-symbol expectancy distribution",
            "Review worst fold and worst symbol",
            "Confirm hard rejects understood",
            "Confirm shadow gate != PAPER_ALLOWED",
            "Do not conclude superiority from aggregate delta_expectancy alone",
            "Explicit human decision required for any lifecycle change",
        ],
        "next_allowed_actions": [
            "KEEP_SHADOW_RESEARCH",
            "REQUEST_MORE_DATA",
            "EXPLICIT_CANDIDATE_REVIEW",
        ],
    }


def run_historical_evidence(
    *,
    symbols: Optional[Sequence[str]] = None,
    max_symbols: Optional[int] = None,
    ohlcv_limit: Optional[int] = None,
    min_trades: int = 10,
    mode: str = "smoke",
    persist_gate: bool = False,
    out_dir: str = "artifacts/crypto/research",
    provider: Optional[BinancePublicProvider] = None,
    bars: Optional[pd.DataFrame] = None,
) -> dict[str, Any]:
    assert_crypto_paper_only()
    mode = (mode or "smoke").strip().lower()
    if mode not in ("smoke", "full"):
        mode = "smoke"
    if max_symbols is None:
        max_symbols = SMOKE_MAX_SYMBOLS if mode == "smoke" else FULL_MAX_SYMBOLS
    if ohlcv_limit is None:
        ohlcv_limit = SMOKE_OHLCV_LIMIT if mode == "smoke" else FULL_OHLCV_LIMIT

    if bars is not None:
        df = bars.copy()
        data_meta = {
            "source": "injected_bars",
            "symbols_ok": sorted(df["symbol"].astype(str).unique().tolist())
            if not df.empty and "symbol" in df.columns
            else [],
            "bars_per_symbol": (
                df.groupby("symbol").size().astype(int).to_dict()
                if not df.empty and "symbol" in df.columns
                else {}
            ),
            "symbols_requested": [],
            "errors": [],
        }
    else:
        df, data_meta = fetch_research_bars(
            symbols=symbols,
            max_symbols=max_symbols,
            ohlcv_limit=ohlcv_limit,
            provider=provider,
        )
        data_meta["source"] = "binance_public"

    report: dict[str, Any] = {
        "plane": PLANE,
        "generated_at": _utc(),
        "live_execution": False,
        "paper_ledger_mutated": False,
        "auto_paper_allowed": False,
        "manual_review_required": True,
        "mode": mode,
        "data": data_meta,
        "status": "PENDING",
    }
    if df is None or df.empty:
        report["status"] = "NO_BARS"
        report["error"] = "No OHLCV available for evidence run"
        _write_report(out_dir, report)
        return report

    period = _period_meta(df)
    cfg = CryptoEvaluatorConfig(min_trades=min_trades)
    comparison = run_shadow_comparison(df, cfg=cfg, persist_gate=persist_gate)
    ref_sym = _per_symbol_stats(df, REFERENCE_ID, cfg)
    sh_sym = _per_symbol_stats(df, SHADOW_ID, cfg)
    fold_ref = (
        (comparison.get("reference") or {})
        .get("evidence", {})
        .get("walk_forward", {})
        .get("fold_consistency")
        or {}
    )
    fold_sh = (
        (comparison.get("shadow") or {})
        .get("evidence", {})
        .get("walk_forward", {})
        .get("fold_consistency")
        or {}
    )
    review = build_manual_review_report(
        comparison=comparison,
        data_meta=data_meta,
        period=period,
        mode=mode,
        ref_symbols=ref_sym,
        shadow_symbols=sh_sym,
        fold_ref=fold_ref if fold_ref else {"n_folds": 0, "note": "see_wfa_windows"},
        fold_shadow=fold_sh if fold_sh else {"n_folds": 0, "note": "see_wfa_windows"},
    )
    report.update(
        {
            "status": "READY_FOR_MANUAL_REVIEW",
            "period": period,
            "comparison": comparison.get("comparison"),
            "reference": comparison.get("reference"),
            "shadow": comparison.get("shadow"),
            "invariants": comparison.get("invariants"),
            "manual_review": review,
            "hard_checks": {
                "reference_hard_reject": review["strategies"]["reference_sma20"]["hard_rejects"],
                "shadow_hard_reject": review["strategies"]["shadow_momentum"]["hard_rejects"],
                "shadow_gate_status": review["strategies"]["shadow_momentum"]["gate_status"],
                "reference_gate_status": review["strategies"]["reference_sma20"]["gate_status"],
                "shadow_paper_eligible": False,
            },
        }
    )
    _write_report(out_dir, report)
    return report


def _write_report(out_dir: str, report: dict[str, Any]) -> None:
    from pathlib import Path

    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "last_evidence_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    mr = report.get("manual_review")
    if mr:
        (path / "manual_review.json").write_text(
            json.dumps(mr, indent=2, default=str), encoding="utf-8"
        )


if __name__ == "__main__":
    assert_crypto_paper_only()
    mode = os.getenv("CRYPTO_EVIDENCE_MODE", "smoke").strip().lower()
    min_tr = int(os.getenv("CRYPTO_EVIDENCE_MIN_TRADES", "5"))
    rep = run_historical_evidence(mode=mode, min_trades=min_tr, persist_gate=False)
    print(
        json.dumps(
            {
                "status": rep.get("status"),
                "mode": rep.get("mode"),
                "manual_review_required": rep.get("manual_review_required"),
                "auto_paper_allowed": rep.get("auto_paper_allowed"),
                "consistency_warnings": (rep.get("manual_review") or {}).get(
                    "consistency_warnings"
                ),
                "comparison": rep.get("comparison"),
                "hard_checks": rep.get("hard_checks"),
            },
            indent=2,
            default=str,
        )
    )
