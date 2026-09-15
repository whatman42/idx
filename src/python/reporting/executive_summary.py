"""LLM Executive Summary — reporting/interpretation layer ONLY.

Never mutates signals, portfolio, risk, or execution. Decision engine remains SSOT.
"""
from __future__ import annotations

import hashlib
import json
import re
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
    """Insight-focused executive summary — no number recompute; avoid repeating dashboard."""
    pf = payload.get("portfolio") or {}
    dec = payload.get("decision") or {}
    risk = payload.get("risk") or {}
    perf = payload.get("performance") or {}
    exits = payload.get("exits") or []
    sigs = payload.get("signals") or {}
    action = str(dec.get("action") or "NO_BUY")
    positions = int(pf.get("positions") or 0)
    exp = pf.get("exposure_pct")
    symbol = dec.get("symbol") or sigs.get("symbol") or ""
    reasons = [str(r) for r in (dec.get("reason_codes") or [])[:3]]
    gate = str(dec.get("risk_gate") or risk.get("status") or "-")
    sys = payload.get("system") or {}
    dq = (payload.get("data_quality") or {}).get("status") or "-"

    anomalies = []
    if risk.get("integrity_ok") is False:
        anomalies.extend([str(b) for b in (risk.get("active_blocks") or [])[:4]])
    if risk.get("status") == "BLOCKED" and not anomalies:
        anomalies.append("status risiko BLOCKED")

    if action == "BUY" and symbol:
        inti = (
            f"1 sinyal BUY {symbol} lolos gate dan menjadi ranking #1 "
            f"pada periode ini."
        )
        if reasons:
            inti += " " + reasons[0]
    elif action == "SELL" and symbol:
        inti = f"Sistem mencatat sinyal SELL {symbol}."
    elif positions == 0:
        inti = (
            "Tidak ada posisi aktif. Tidak ada sinyal yang memenuhi "
            "seluruh syarat pembelian pada periode ini."
        )
    else:
        inti = f"Tidak ada pembelian baru. {positions} posisi tetap dipegang."

    if positions == 0:
        port = "Tidak ada posisi aktif; exposure 0%."
    else:
        exp_s = f"{float(exp):.2f}%" if exp is not None else "-"
        port = f"{positions} posisi aktif dengan exposure {exp_s}."
        upnl = pf.get("unrealized_pnl")
        if upnl is not None:
            try:
                port += f" Unrealized P/L (dari state): Rp{float(upnl):,.0f}".replace(",", ".")
            except Exception:
                pass

    if exits:
        performa = f"{len(exits)} exit tercatat pada periode ini."
    elif int(perf.get("trades") or 0) < 5 and not exits:
        performa = (
            "Belum dapat dinilai secara representatif — sampel trade selesai masih kecil "
            "atau belum ada exit."
        )
    elif perf:
        performa = "Metrik performa tersedia di state; lihat field performance (bukan prediksi)."
    else:
        performa = "Belum ada trade yang selesai (exit); performa bot belum dapat dinilai."

    notes = []
    if anomalies:
        notes.append("ANOMALI DATA: " + "; ".join(anomalies))
    if action == "BUY":
        notes.append("Sinyal BUY bukan jaminan profit.")
        notes.append("Tidak ada order yang dikirim ke broker.")
    if int(perf.get("trades") or 0) < 5 and not exits:
        notes.append("Sampel performa masih terlalu kecil.")
    if dq.upper() in ("FAIL", "WARN"):
        notes.append(f"Kualitas data: {dq}.")
    if not notes:
        notes.append("Tidak ada anomali material yang dilaporkan dari data yang tersedia.")

    risk_label = str(risk.get("status") or gate or "NORMAL")
    if risk_label.upper() in ("PASS", "OK", ""):
        risk_label = "PASS"
    status = f"Sistem {risk_label if risk_label not in ('PASS',) else 'NORMAL'} • Risk Gate {gate} • Signal Only"
    if sys.get("live_execution") is False or sys.get("signal_only"):
        status += " • NO LIVE EXECUTION"

    lines = [
        "🧠 RINGKASAN EKSEKUTIF",
        "📌 Inti",
        inti,
        "💰 Portofolio",
        port,
        "📈 Performa",
        performa,
        "⚠️ Perlu diperhatikan",
    ]
    for n in notes:
        lines.append(f"• {n}")
    lines += ["🎯 Status", status]
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

    banned_phrases = (
        "RISIKO TERKENDALI",
        "RISIKO AMAN",
        "INVESTASI AMAN",
        "PASTI UNTUNG",
        "SANGAT AMAN",
        "OPTIMAL",
        "MENGUNTUNGKAN",
    )
    for bp in banned_phrases:
        if bp in upper:
            errs.append("exec_marketing_language")
            break

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

    needed = ["INTI", "PORTOFOLIO", "STATUS"]
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
