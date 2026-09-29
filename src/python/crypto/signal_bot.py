"""Crypto paper signal bot — isolated ops entry. No live orders. No IDX state."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.python.crypto.config import (
    CRYPTO_ENABLED,
    CRYPTO_INITIAL_CAPITAL_USDT,
    CRYPTO_MAX_POSITIONS,
    CRYPTO_STATE_PATH,
    assert_crypto_paper_only,
    crypto_sim_assumptions,
)
from src.python.crypto.paper_ledger import CryptoPaperLedger
from src.python.crypto.provider import BinancePublicProvider
from src.python.crypto.risk import evaluate_crypto_entry
from src.python.crypto.strategy import STRATEGY_ID, STRATEGY_VERSION, crypto_sma20_signals
from src.python.crypto.universe import CryptoUniverseProvider


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_crypto_paper(
    *,
    max_symbols: int = 80,
    ohlcv_limit: int = 60,
    reset: bool = False,
    state_path: Optional[str] = None,
    provider: Optional[BinancePublicProvider] = None,
) -> dict[str, Any]:
    """Discover USDT universe, score subset with OHLCV, paper-fill, report.

    Full discovery is always reported; OHLCV fetch is capped for Actions runtime.
    """
    assert_crypto_paper_only()
    if not CRYPTO_ENABLED:
        return {"status": "DISABLED", "live_execution": False}

    prov = provider or BinancePublicProvider()
    uni = CryptoUniverseProvider(prov)
    discovery = uni.discover()
    if discovery.discovered_count == 0 and discovery.errors:
        return {
            "status": "FAIL_CLOSED_PROVIDER",
            "live_execution": False,
            "universe": discovery.to_dict(),
        }

    path = state_path or CRYPTO_STATE_PATH
    ledger = CryptoPaperLedger.new_session() if reset else CryptoPaperLedger.load(path)

    # Cap OHLCV work for CI/Actions; universe report still full
    candidates = discovery.eligible[: max(1, max_symbols)]
    frames: list[pd.DataFrame] = []
    ohlcv_errors: list[str] = []
    for inst in candidates:
        try:
            bars = prov.fetch_ohlcv(inst.symbol, interval="1d", limit=ohlcv_limit, raw_symbol=inst.raw_symbol)
            if not bars:
                ohlcv_errors.append(f"{inst.symbol}:OHLCV_EMPTY")
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
        except Exception as e:
            ohlcv_errors.append(f"{inst.symbol}:{type(e).__name__}")

    signals: list[dict[str, Any]] = []
    if frames:
        all_bars = pd.concat(frames, ignore_index=True)
        signals = crypto_sma20_signals(all_bars)

    marks = {}
    for f in frames:
        sym = str(f.iloc[-1]["symbol"])
        marks[sym] = float(f.iloc[-1]["close"])

    fills: list[dict[str, Any]] = []
    risk_skips = 0
    for sig in signals:
        if len(ledger.positions) >= CRYPTO_MAX_POSITIONS:
            break
        sym = sig["symbol"]
        if sym in ledger.positions:
            continue
        px = float(sig["price"])
        rd = evaluate_crypto_entry(
            equity_usdt=ledger.equity(marks),
            open_count=len(ledger.positions),
            symbol=sym,
            price=px,
        )
        if not rd.allow:
            risk_skips += 1
            continue
        notional = ledger.equity(marks) * rd.weight
        inst_meta = next((i for i in candidates if i.symbol == sym), None)
        sid = f"crypto_{sig['timestamp'][:10]}_{sym}_{STRATEGY_VERSION}"
        fill = ledger.apply_buy(
            symbol=sym,
            price=px,
            notional_usdt=notional,
            signal_id=sid,
            timestamp=sig.get("timestamp") or _utc(),
            min_qty=float(inst_meta.min_quantity) if inst_meta else 0.0,
            min_notional=float(inst_meta.min_notional) if inst_meta else 0.0,
            qty_precision=int(inst_meta.quantity_precision) if inst_meta else 8,
        )
        fills.append(fill)
        if fill.get("status") == "CRYPTO_PAPER_FILL":
            marks[sym] = float(fill["price"])

    ledger.save(path)
    summary = ledger.to_dict(marks)

    report = {
        "status": "SUCCESS",
        "market": "CRYPTO",
        "tag": "[CRYPTO PAPER]",
        "live_execution": False,
        "base_currency": "USDT",
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "universe": discovery.to_dict(),
        "ohlcv_scanned": len(candidates),
        "ohlcv_errors": ohlcv_errors[:50],
        "signals": signals[:30],
        "signals_count": len(signals),
        "fills": fills,
        "risk_skips": risk_skips,
        "portfolio": summary,
        "simulation": crypto_sim_assumptions(),
        "generated_at": _utc(),
    }
    out_dir = Path("artifacts/crypto")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "last_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report


def format_crypto_telegram(report: dict[str, Any]) -> str:
    """Presentation only — ledger remains SSOT."""
    uni = report.get("universe") or {}
    pf = report.get("portfolio") or {}
    lines = [
        "[CRYPTO PAPER]",
        f"status: {report.get('status')}",
        f"live_execution: false",
        f"base: USDT",
        f"strategy: {report.get('strategy_id')}@{report.get('strategy_version')}",
        f"universe discovered: {uni.get('discovered_count')}",
        f"eligible USDT: {uni.get('eligible_count')}",
        f"blocked: {uni.get('blocked_count')}",
        f"signals: {report.get('signals_count')}",
        f"fills: {sum(1 for f in (report.get('fills') or []) if f.get('status')=='CRYPTO_PAPER_FILL')}",
        f"equity_USDT: {pf.get('equity')}",
        f"cash_USDT: {pf.get('cash')}",
        f"positions: {len(pf.get('positions') or {})}",
    ]
    for f in report.get("fills") or []:
        if f.get("status") == "CRYPTO_PAPER_FILL":
            lines.append(f"  FILL {f.get('symbol')} qty={f.get('qty')} @ {f.get('price')}")
    lines.append("Broker: tidak dikirim — NO LIVE EXECUTION")
    return "\n".join(lines)


if __name__ == "__main__":
    assert_crypto_paper_only()
    reset = os.getenv("CRYPTO_RESET", "").strip() in ("1", "true", "TRUE")
    max_sym = int(os.getenv("CRYPTO_MAX_SYMBOLS", "40"))
    rep = run_crypto_paper(max_symbols=max_sym, reset=reset)
    print(json.dumps({k: rep[k] for k in ("status", "live_execution", "base_currency", "signals_count", "universe") if k in rep}, indent=2))
    print(format_crypto_telegram(rep))
