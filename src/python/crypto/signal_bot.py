"""Crypto paper signal bot — isolated ops entry. No live orders. No IDX state.

Coverage contract:
  - Universe discovery = ALL provider instruments (full */USDT eligible set).
  - Signal/OHLCV processing default = ALL eligible (max_symbols=0).
  - CRYPTO_MAX_SYMBOLS > 0 is TEST/debug sampling only and is reported explicitly
    as signal_coverage_mode=SAMPLED so paper results are not mistaken for 496/496.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.python.crypto.config import (
    CRYPTO_ENABLED,
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


def _ledger_lock_path(state_path: str) -> Path:
    return Path(str(state_path) + ".lock")


def _acquire_lock(state_path: str, *, timeout_sec: float = 60.0) -> Path:
    """Best-effort exclusive lock for Actions concurrency (dispatch vs schedule)."""
    lock = _ledger_lock_path(state_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, f"{os.getpid()}|{_utc()}".encode())
            os.close(fd)
            return lock
        except FileExistsError:
            try:
                age = time.time() - lock.stat().st_mtime
                if age > 900:
                    lock.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            time.sleep(0.5)
    raise RuntimeError(f"CRYPTO_LEDGER_LOCK_TIMEOUT:{lock}")


def _release_lock(lock: Path) -> None:
    try:
        lock.unlink(missing_ok=True)
    except OSError:
        pass


def run_crypto_paper(
    *,
    max_symbols: int = 0,
    ohlcv_limit: int = 60,
    reset: bool = False,
    state_path: Optional[str] = None,
    provider: Optional[BinancePublicProvider] = None,
) -> dict[str, Any]:
    """Discover full USDT universe and process eligible pairs for paper signals."""
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
            "signal_coverage_mode": "NONE",
            "signal_coverage": "0/0",
        }

    eligible_all = list(discovery.eligible)
    n_eligible = len(eligible_all)
    if max_symbols and max_symbols > 0:
        candidates = eligible_all[:max_symbols]
        coverage_mode = "SAMPLED"
    else:
        candidates = eligible_all
        coverage_mode = "FULL_ELIGIBLE"

    path = state_path or CRYPTO_STATE_PATH
    lock = _acquire_lock(path)
    try:
        ledger = CryptoPaperLedger.new_session() if reset else CryptoPaperLedger.load(path)

        frames: list[pd.DataFrame] = []
        ohlcv_errors: list[str] = []
        ohlcv_ok = 0
        for inst in candidates:
            try:
                bars = prov.fetch_ohlcv(
                    inst.symbol,
                    interval="1d",
                    limit=ohlcv_limit,
                    raw_symbol=inst.raw_symbol,
                )
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
                ohlcv_ok += 1
            except Exception as e:
                ohlcv_errors.append(f"{inst.symbol}:{type(e).__name__}")
                if "429" in str(e) or "Rate" in type(e).__name__:
                    time.sleep(1.0)

        signals: list[dict[str, Any]] = []
        if frames:
            all_bars = pd.concat(frames, ignore_index=True)
            signals = crypto_sma20_signals(all_bars)

        marks: dict[str, float] = {}
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
            sid = f"crypto_{str(sig.get('timestamp', ''))[:10]}_{sym}_{STRATEGY_VERSION}"
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
    finally:
        _release_lock(lock)

    n_cand = len(candidates)
    report = {
        "status": "SUCCESS",
        "market": "CRYPTO",
        "tag": "[CRYPTO PAPER]",
        "live_execution": False,
        "base_currency": "USDT",
        "strategy_id": STRATEGY_ID,
        "strategy_version": STRATEGY_VERSION,
        "universe": discovery.to_dict(),
        "signal_coverage_mode": coverage_mode,
        "signal_coverage": f"{n_cand}/{n_eligible}",
        "ohlcv_attempted": n_cand,
        "ohlcv_ok": ohlcv_ok,
        "ohlcv_errors": ohlcv_errors[:100],
        "ohlcv_error_count": len(ohlcv_errors),
        "signals": signals[:50],
        "signals_count": len(signals),
        "fills": fills,
        "fills_paper": sum(1 for f in fills if f.get("status") == "CRYPTO_PAPER_FILL"),
        "risk_skips": risk_skips,
        "portfolio": summary,
        "simulation": crypto_sim_assumptions(),
        "endpoint_used": getattr(prov, "endpoint_used", ""),
        "endpoint_fallback_used": bool(getattr(prov, "endpoint_fallback_used", False)),
        "generated_at": _utc(),
    }

    # Research memory (Turso/SQLite) — optional; never blocks paper
    try:
        from src.python.crypto.research_memory import get_crypto_research_memory

        mem = get_crypto_research_memory()
        mem_result = mem.record_cycle(report)
        report["research_memory"] = mem_result
        if mem.status.value != "UNAVAILABLE":
            mem.record_strategy_version(
                str(report.get("strategy_id") or "crypto_rule_sma20"),
                str(report.get("strategy_version") or "crypto_sma_v0"),
                lifecycle="RESEARCH",
                notes="paper_cycle",
            )
        mem.close()
    except Exception as e:
        report["research_memory"] = {
            "ok": False,
            "reason": f"soft_fail:{type(e).__name__}",
            "paper_blocked": False,
        }

    out_dir = Path("artifacts/crypto")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "last_report.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    return report


def format_crypto_telegram(report: dict[str, Any]) -> str:
    """Pesan Telegram [CRYPTO PAPER] — presentasi saja; ledger tetap SSOT."""
    uni = report.get("universe") or {}
    pf = report.get("portfolio") or {}
    status = str(report.get("status") or "")
    status_id = "BERHASIL" if status.upper() in ("SUCCESS", "OK", "BERHASIL") else status

    def _fmt_px(x: float) -> str:
        try:
            v = float(x)
        except (TypeError, ValueError):
            return str(x)
        if v >= 100:
            return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        if v >= 1:
            return f"{v:,.4f}".rstrip("0").rstrip(".").replace(".", ",")
        s = f"{v:.10f}".rstrip("0").rstrip(".")
        return s.replace(".", ",")

    def _fmt_qty(x: float) -> str:
        try:
            v = float(x)
        except (TypeError, ValueError):
            return str(x)
        if abs(v - round(v)) < 1e-9:
            return f"{int(round(v)):,}".replace(",", ".")
        s = f"{v:,.6f}".rstrip("0").rstrip(".")
        return s.replace(",", "X").replace(".", ",").replace("X", ".")

    def _fmt_usdt(x: float) -> str:
        try:
            v = float(x)
        except (TypeError, ValueError):
            return str(x)
        return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    equity = float(pf.get("equity") or 0)
    cash = float(pf.get("cash") or 0)
    mv = float(pf.get("market_value") or (equity - cash))
    n_elig = uni.get("eligible_count") or report.get("ohlcv_attempted") or 0
    ohlcv_ok = report.get("ohlcv_ok")
    ohlcv_att = report.get("ohlcv_attempted")
    data_line = f"{ohlcv_ok}/{ohlcv_att}" if ohlcv_ok is not None else str(n_elig)
    cov = report.get("signal_coverage") or data_line
    mode = report.get("signal_coverage_mode") or ""
    pasar_extra = f" (sampel {cov})" if mode == "SAMPLED" else ""

    lines = [
        "[CRYPTO PAPER]",
        "",
        f"Status: {status_id}",
        "Mode: SIMULASI — tidak ada transaksi nyata",
        "Modal: USDT",
        f"Strategi: SMA20 ({report.get('strategy_id') or 'crypto_rule_sma20'})",
        "",
        "Pasar diperiksa:",
        f"• {n_elig} aset USDT{pasar_extra}",
        f"• Data tersedia: {data_line}",
        f"• Sinyal: {report.get('signals_count') or 0}",
        f"• Posisi dibuka: {report.get('fills_paper') or len(pf.get('positions') or {})}",
        "",
        "Portofolio:",
        f"• Kas: {_fmt_usdt(cash)} USDT",
        f"• Nilai posisi: {_fmt_usdt(mv)} USDT",
        f"• Total aset: {_fmt_usdt(equity)} USDT",
        "",
        "POSISI SIMULASI",
        "",
    ]

    positions = pf.get("positions") or {}
    if positions:
        for sym, row in positions.items():
            if isinstance(row, dict):
                entry = float(row.get("avg_entry") or row.get("entry_price") or 0)
                qty = float(row.get("qty") or 0)
                tp = float(row.get("tp") or 0)
                sl = float(row.get("sl") or 0)
            else:
                entry = float(getattr(row, "avg_entry", 0) or 0)
                qty = float(getattr(row, "qty", 0) or 0)
                tp = float(getattr(row, "tp", 0) or 0)
                sl = float(getattr(row, "sl", 0) or 0)
            lines.append(str(sym))
            lines.append(f"Beli: {_fmt_px(entry)}")
            lines.append(f"TP: {_fmt_px(tp) if tp else '—'}")
            lines.append(f"SL: {_fmt_px(sl) if sl else '—'}")
            lines.append(f"Jumlah: {_fmt_qty(qty)}")
            lines.append("")
    else:
        for f in report.get("fills") or []:
            if f.get("status") != "CRYPTO_PAPER_FILL":
                continue
            lines.append(str(f.get("symbol")))
            lines.append(f"Beli: {_fmt_px(f.get('price') or 0)}")
            lines.append(f"TP: {_fmt_px(f.get('tp') or 0) if f.get('tp') else '—'}")
            lines.append(f"SL: {_fmt_px(f.get('sl') or 0) if f.get('sl') else '—'}")
            lines.append(f"Jumlah: {_fmt_qty(f.get('qty') or 0)}")
            lines.append("")

    lines.extend(
        [
            "Catatan:",
            "TP = target harga untuk mengambil keuntungan.",
            "SL = batas harga untuk membatasi kerugian.",
            "",
            "Semua transaksi hanya simulasi.",
            "Tidak ada order yang dikirim ke exchange.",
        ]
    )
    return "\n".join(lines)


def maybe_send_telegram(text: str) -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    allow = os.getenv("CRYPTO_TELEGRAM_ALLOW", os.getenv("IDX_TELEGRAM_ALLOW_PAPER", "")).strip()
    if not token or not chat or allow not in ("1", "true", "TRUE", "yes"):
        return "SKIPPED_NO_CONFIG"
    try:
        import httpx

        r = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text[:4000]},
            timeout=30.0,
        )
        if r.status_code == 200:
            return "SENT"
        return f"HTTP_{r.status_code}"
    except Exception as e:
        return f"ERROR:{type(e).__name__}"


if __name__ == "__main__":
    assert_crypto_paper_only()
    reset = os.getenv("CRYPTO_RESET", "").strip() in ("1", "true", "TRUE")
    max_sym = int(os.getenv("CRYPTO_MAX_SYMBOLS", "0"))
    rep = run_crypto_paper(max_symbols=max_sym, reset=reset)
    msg = format_crypto_telegram(rep)
    tg = maybe_send_telegram(msg)
    rep["telegram_status"] = tg
    Path("artifacts/crypto").mkdir(parents=True, exist_ok=True)
    Path("artifacts/crypto/last_report.json").write_text(
        json.dumps(rep, indent=2, default=str), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                k: rep.get(k)
                for k in (
                    "status",
                    "live_execution",
                    "base_currency",
                    "signal_coverage_mode",
                    "signal_coverage",
                    "ohlcv_ok",
                    "ohlcv_attempted",
                    "signals_count",
                    "fills_paper",
                    "telegram_status",
                    "endpoint_used",
                    "research_memory",
                )
            },
            indent=2,
        )
    )
    print(msg)
