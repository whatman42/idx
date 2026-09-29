"""P3+ real historical evidence runner — research plane only.

Order (mandatory):
  real OHLCV → FeatureSnapshot → ref+shadow → WFA/backtest
  → EvidencePackage → PromotionGate → report for MANUAL review

Never auto PAPER_ALLOWED. Never LIVE_EXECUTION. Never mutates paper ledger.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd

from src.python.crypto.config import assert_crypto_paper_only
from src.python.crypto.evaluator import CryptoEvaluatorConfig
from src.python.crypto.provider import BinancePublicProvider
from src.python.crypto.shadow_eval import run_shadow_comparison
from src.python.crypto.universe import CryptoUniverseProvider

PLANE = "CRYPTO_RESEARCH_EVIDENCE"


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
        except Exception as e:
            meta["errors"].append(f"{sym}:{type(e).__name__}")

    meta["endpoint_used"] = getattr(prov, "endpoint_used", "")
    if not frames:
        return pd.DataFrame(), meta
    return pd.concat(frames, ignore_index=True), meta


def run_historical_evidence(
    *,
    symbols: Optional[Sequence[str]] = None,
    max_symbols: int = 12,
    ohlcv_limit: int = 120,
    min_trades: int = 10,
    persist_gate: bool = False,
    out_dir: str = "artifacts/crypto/research",
    provider: Optional[BinancePublicProvider] = None,
    bars: Optional[pd.DataFrame] = None,
) -> dict[str, Any]:
    assert_crypto_paper_only()

    if bars is not None:
        df = bars.copy()
        data_meta = {
            "source": "injected_bars",
            "symbols_ok": sorted(df["symbol"].astype(str).unique().tolist())
            if not df.empty and "symbol" in df.columns
            else [],
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
        "data": data_meta,
        "status": "PENDING",
    }

    if df is None or df.empty:
        report["status"] = "NO_BARS"
        report["error"] = "No OHLCV available for evidence run"
        _write_report(out_dir, report)
        return report

    cfg = CryptoEvaluatorConfig(min_trades=min_trades)
    comparison = run_shadow_comparison(df, cfg=cfg, persist_gate=persist_gate)

    hard = {
        "reference_hard_reject": list(
            (comparison.get("reference") or {}).get("evidence", {}).get("hard_reject") or []
        ),
        "shadow_hard_reject": list(
            (comparison.get("shadow") or {}).get("evidence", {}).get("hard_reject") or []
        ),
        "shadow_gate_status": (comparison.get("shadow") or {}).get("gate", {}).get(
            "lifecycle_status"
        ),
        "reference_gate_status": (comparison.get("reference") or {}).get("gate", {}).get(
            "lifecycle_status"
        ),
        "shadow_paper_eligible": False,
    }

    report.update(
        {
            "status": "READY_FOR_MANUAL_REVIEW",
            "comparison": comparison.get("comparison"),
            "reference": comparison.get("reference"),
            "shadow": comparison.get("shadow"),
            "invariants": comparison.get("invariants"),
            "hard_checks": hard,
            "review_checklist": [
                "Verify data coverage and symbol set",
                "Compare expectancy / n_trades / max_drawdown ref vs shadow",
                "Confirm hard_reject empty or understood",
                "Confirm shadow gate != PAPER_ALLOWED",
                "Explicit human decision required for any lifecycle change",
            ],
            "next_allowed_actions": [
                "KEEP_SHADOW_RESEARCH",
                "REQUEST_MORE_DATA",
                "EXPLICIT_CANDIDATE_REVIEW",
            ],
        }
    )
    _write_report(out_dir, report)
    return report


def _write_report(out_dir: str, report: dict[str, Any]) -> None:
    path = Path(out_dir)
    path.mkdir(parents=True, exist_ok=True)
    (path / "last_evidence_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    assert_crypto_paper_only()
    max_sym = int(os.getenv("CRYPTO_EVIDENCE_MAX_SYMBOLS", "8"))
    limit = int(os.getenv("CRYPTO_EVIDENCE_OHLCV_LIMIT", "90"))
    min_tr = int(os.getenv("CRYPTO_EVIDENCE_MIN_TRADES", "5"))
    rep = run_historical_evidence(
        max_symbols=max_sym,
        ohlcv_limit=limit,
        min_trades=min_tr,
        persist_gate=False,
    )
    print(
        json.dumps(
            {
                "status": rep.get("status"),
                "live_execution": rep.get("live_execution"),
                "auto_paper_allowed": rep.get("auto_paper_allowed"),
                "manual_review_required": rep.get("manual_review_required"),
                "symbols_ok": (rep.get("data") or {}).get("symbols_ok"),
                "comparison": rep.get("comparison"),
                "hard_checks": rep.get("hard_checks"),
            },
            indent=2,
            default=str,
        )
    )
