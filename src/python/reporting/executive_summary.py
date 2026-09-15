"""LLM Executive Summary — reporting/interpretation layer ONLY.

Never mutates signals, portfolio, risk, or execution. Decision engine remains SSOT.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from src.python.reporting.models import CycleReport

MAX_WORDS = 180
MAX_CHARS = 1800


@dataclass
class ExecutiveObservability:
    request_ts: float = 0.0
    model: str = ""
    input_fingerprint: str = ""
    latency_sec: float = 0.0
    success: bool = False
    validation_ok: bool = False
    validation_errors: list[str] = field(default_factory=list)
    fallback_used: bool = False
    output_length: int = 0
    error_category: str = ""
    source: str = "deterministic"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_executive_payload(
    report: CycleReport,
    *,
    performance: Optional[dict[str, Any]] = None,
    previous: Optional[dict[str, Any]] = None,
    system_extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Structured input for LLM. Only fields that exist are included."""
    pf = report.portfolio
    sig = report.signal

    portfolio: dict[str, Any] = {}
    if pf:
        total_pnl = float(pf.realized_pnl or 0) + float(pf.unrealized_pnl or 0)
        base = float(pf.initial_capital or 0)
        ret_pct = (total_pnl / base * 100.0) if base > 0 else None
        portfolio = {
            "equity": pf.equity,
            "cash": pf.cash,
            "exposure_pct": pf.exposure_pct,
            "positions": len(pf.open_positions or []),
            "realized_pnl": pf.realized_pnl,
            "unrealized_pnl": pf.unrealized_pnl,
            "return_pct": ret_pct,
            "initial_capital": pf.initial_capital or None,
            "position_symbols": [p.symbol for p in (pf.open_positions or [])],
        }
        portfolio = {k: v for k, v in portfolio.items() if v is not None}

    signals: dict[str, Any] = {"received": 0, "qualified": 0, "buy": 0, "sell": 0}
    if sig and sig.decision == "BUY":
        signals = {"received": 1, "qualified": 1, "buy": 1, "sell": 0, "symbol": sig.symbol}
    elif sig and sig.decision == "SELL":
        signals = {"received": 1, "qualified": 1, "buy": 0, "sell": 1, "symbol": sig.symbol}

    if sig and sig.decision == "BUY":
        action = "BUY"
        reason_codes = list(sig.explanation_context or report.no_signal_reasons or [])
    elif sig and sig.decision == "SELL":
        action = "SELL"
        reason_codes = list(sig.explanation_context or [])
    else:
        action = "NO_BUY"
        reason_codes = list(report.no_signal_reasons or [])

    decision = {
        "action": action,
        "reason_codes": reason_codes[:8],
        "risk_gate": report.risk_gate,
        "status": report.status,
    }
    if sig and sig.decision in ("BUY", "SELL"):
        decision["symbol"] = sig.symbol
        if sig.fill_status:
            decision["fill_status"] = sig.fill_status

    risk = {
        "status": "NORMAL" if (report.risk_gate or "PASS").upper() in ("PASS", "OK", "") else report.risk_gate,
        "active_blocks": [],
        "integrity_ok": report.integrity_ok,
    }
    if not report.integrity_ok:
        risk["status"] = "BLOCKED"
        risk["active_blocks"] = list(report.integrity_errors or [])[:8]
    elif (report.risk_gate or "").upper() in ("BLOCKED", "FAIL", "FAILED"):
        risk["status"] = "BLOCKED"
        risk["active_blocks"] = [f"risk_gate:{report.risk_gate}"]

    exits = []
    for e in report.exits or []:
        exits.append(
            {
                "symbol": e.symbol,
                "exit_reason": e.exit_reason,
                "realized_pnl": e.realized_pnl,
                "pnl_pct": e.pnl_pct,
            }
        )

    dq = {"status": report.dq_status or "UNKNOWN"}

    system = {
        "engine_version": report.model_version or "",
        "mode": report.mode,
        "signal_only": report.signal_only,
        "live_execution": report.live_execution,
        "data_source": report.data_source or "",
        "governor_action": report.governor_action or "",
    }
    if system_extra:
        for k, v in system_extra.items():
            if v is not None and k not in system:
                system[k] = v

    payload: dict[str, Any] = {
        "timestamp": report.trading_date,
        "portfolio": portfolio,
        "signals": signals,
        "decision": decision,
        "risk": risk,
        "data_quality": dq,
        "system": system,
        "exits": exits,
    }
    if performance:
        clean_perf = {k: v for k, v in performance.items() if v is not None}
        if clean_perf:
            payload["performance"] = clean_perf
    if previous:
        payload["previous"] = {k: v for k, v in previous.items() if v is not None}

    return payload


def payload_fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def deterministic_executive_summary(payload: dict[str, Any]) -> str:
    """Template executive summary — no LLM. Used as fallback and default."""
    pf = payload.get("portfolio") or {}
    dec = payload.get("decision") or {}
    risk = payload.get("risk") or {}
    perf = payload.get("performance") or {}
    exits = payload.get("exits") or []
    action = str(dec.get("action") or "NO_BUY")

    equity = pf.get("equity")
    cash = pf.get("cash")
    exp = pf.get("exposure_pct")
    positions = pf.get("positions", 0)
    ret = pf.get("return_pct")

    def rp(x):
        if x is None:
            return "tidak tersedia"
        try:
            return f"Rp{float(x):,.0f}".replace(",", ".")
        except Exception:
            return "tidak tersedia"

    if positions == 0 and float(exp or 0) <= 0.01:
        inti = "Bot saat ini tidak memiliki posisi saham dan modal masih dalam bentuk kas. "
    else:
        inti = f"Bot memiliki {positions} posisi dengan dana terpakai {exp if exp is not None else '-'}%. "

    if action == "NO_BUY":
        inti += "Tidak ada sinyal yang memenuhi seluruh persyaratan pembelian pada periode ini."
    elif action == "BUY":
        inti += f"Sistem mencatat keputusan BUY pada {dec.get('symbol', 'simbol terkait')}."
    elif action == "SELL":
        inti += f"Sistem mencatat keputusan SELL pada {dec.get('symbol', 'simbol terkait')}."

    reasons = dec.get("reason_codes") or []
    if action == "NO_BUY":
        keputusan = "Tidak ada pembelian. Sistem mempertahankan modal tanpa membuka posisi baru."
        if reasons:
            keputusan += " Alasan sistem: " + "; ".join(str(r) for r in reasons[:3]) + "."
    elif action == "BUY":
        keputusan = f"BUY {dec.get('symbol', '')} sesuai decision engine."
        if reasons:
            keputusan += " " + "; ".join(str(r) for r in reasons[:3])
    else:
        keputusan = f"{action} {dec.get('symbol', '')} sesuai decision engine."

    port_line = f"Ekuitas {rp(equity)}, kas {rp(cash)}"
    if exp is not None:
        port_line += f", dana terpakai {float(exp):.2f}%"
    if ret is not None:
        port_line += f", return {float(ret):.2f}%"
    port_line += f", posisi aktif: {positions}."

    if not perf and not exits and positions == 0 and action == "NO_BUY":
        performa = "Belum ada transaksi pada periode ini, sehingga performa trading belum dapat dinilai."
    elif exits:
        performa = f"Terdapat {len(exits)} exit pada periode ini."
        for e in exits[:2]:
            performa += f" {e.get('symbol')}: P/L {rp(e.get('realized_pnl'))} ({e.get('exit_reason')})."
    elif perf:
        parts = []
        for key in (
            "daily_return_pct",
            "weekly_return_pct",
            "win_rate",
            "profit_factor",
            "max_drawdown_pct",
            "trades",
        ):
            if key in perf and perf[key] is not None:
                parts.append(f"{key}={perf[key]}")
        performa = (
            "Metrik yang tersedia: " + ", ".join(parts)
            if parts
            else "Data performa terbatas; belum cukup representatif."
        )
        if int(perf.get("trades") or 0) < 5:
            performa += " Jumlah sampel masih kecil."
    else:
        performa = "Data tidak cukup untuk menilai performa bot secara lengkap."

    blocks = risk.get("active_blocks") or []
    if risk.get("status") == "BLOCKED" or blocks:
        perhatian = (
            "Status risiko/blocked: " + "; ".join(str(b) for b in blocks[:4])
            if blocks
            else "Status risiko BLOCKED."
        )
    elif (payload.get("data_quality") or {}).get("status", "").upper() in ("FAIL", "WARN"):
        perhatian = f"Kualitas data: {(payload.get('data_quality') or {}).get('status')}."
    else:
        perhatian = "Tidak ada anomali material yang dilaporkan dari data yang tersedia."

    if action == "NO_BUY" and positions == 0:
        kesimpulan = (
            "Sistem berada dalam kondisi menunggu dan tidak mengambil posisi "
            "karena belum ada sinyal yang memenuhi persyaratan."
        )
    elif action == "BUY":
        kesimpulan = (
            "Keputusan BUY berasal dari decision engine; ringkasan ini hanya interpretasi, "
            "bukan order live."
        )
    else:
        kesimpulan = "Ringkasan ini merefleksikan state sistem; bukan rekomendasi trading baru."

    sys = payload.get("system") or {}
    if sys.get("live_execution") is False or sys.get("signal_only"):
        kesimpulan += " Mode: SIGNAL ONLY — NO LIVE EXECUTION."

    lines = [
        "🧠 INTI LAPORAN",
        "",
        inti,
        "",
        "📌 KEPUTUSAN",
        keputusan,
        "",
        "💰 PORTOFOLIO",
        port_line,
        "",
        "📈 PERFORMA BOT",
        performa,
        "",
        "⚠️ PERLU DIPERHATIKAN",
        perhatian,
        "",
        "🎯 KESIMPULAN",
        kesimpulan,
    ]
    return "\n".join(lines)


def validate_executive_text(text: str, payload: dict[str, Any]) -> list[str]:
    errs: list[str] = []
    if not text or not text.strip():
        return ["exec_empty"]
    if len(text) > MAX_CHARS:
        errs.append("exec_too_long")
    words = len(text.split())
    if words > MAX_WORDS + 40:
        errs.append("exec_word_limit")

    upper = text.upper()
    action = str((payload.get("decision") or {}).get("action") or "NO_BUY")

    if action == "NO_BUY":
        if re.search(r"\b(REKOMENDASI\s+BUY|SARAN\s+BUY|HARUS\s+BELI|BELI\s+SEKARANG)\b", upper):
            errs.append("exec_unauthorized_buy_recommendation")
        if re.search(r"\b(REKOMENDASI\s+SELL|SARAN\s+SELL|HARUS\s+JUAL)\b", upper):
            errs.append("exec_unauthorized_sell_recommendation")

    sys = payload.get("system") or {}
    if not sys.get("live_execution"):
        if re.search(r"\bORDER\s+TELAH\s+DIKIRIM\b|\bBROKER\s+FILLED\b|\bLIVE\s+ORDER\s+SENT\b", upper):
            errs.append("exec_false_live_claim")
        if re.search(r"(?<!NO )\bLIVE\s+EXECUTION\b", upper) and "NO LIVE EXECUTION" not in upper:
            errs.append("exec_false_live_claim")

    positions = int((payload.get("portfolio") or {}).get("positions") or 0)
    if positions == 0:
        if re.search(r"SEDANG\s+MEMEGANG", upper) and "TIDAK" not in upper and "BELUM" not in upper:
            errs.append("exec_false_position_claim")

    equity = (payload.get("portfolio") or {}).get("equity")
    if equity is not None:
        for m in re.finditer(r"Rp\s*([\d.]+)", text):
            raw = m.group(1).replace(".", "")
            try:
                val = float(raw)
                if val > 0 and equity > 0 and val > max(equity * 2, 1_000_000) and val > equity * 5:
                    errs.append("exec_suspicious_amount")
                    break
            except Exception:
                pass

    needed = ["INTI", "KEPUTUSAN", "PORTOFOLIO"]
    missing = [h for h in needed if h not in upper]
    if len(missing) >= 2:
        errs.append("exec_missing_sections")

    return errs


_LAST_FP: dict[str, str] = {}


def should_emit_summary(fingerprint: str, *, channel: str = "telegram") -> bool:
    prev = _LAST_FP.get(channel)
    if prev and prev == fingerprint:
        return False
    return True


def mark_emitted(fingerprint: str, *, channel: str = "telegram") -> None:
    _LAST_FP[channel] = fingerprint


def reset_summary_cache() -> None:
    _LAST_FP.clear()
