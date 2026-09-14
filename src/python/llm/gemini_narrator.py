"""Gemini Flash-Lite narrator for Telegram (advisory only).

Every outbound Telegram body should pass through narrate_* helpers.
Does NOT generate trade signals, size, or promotion decisions.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import httpx

DEFAULT_MODEL = "gemini-3.5-flash-lite"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"

SYSTEM_RULES = """Kamu adalah narrator operasional sistem IDX (paper trading, SIGNAL ONLY).
Aturan wajib:
- Bahasa Indonesia, netral, profesional, ringkas (maks ~1200 karakter).
- Format pesan seperti DASHBOARD PORTOFOLIO yang mudah dibaca di Telegram (teks polos).
- Untuk sinyal: fokus HANYA top-1. Sebutkan simbol, harga entry, lot, total pembelian, TP, SL, dan alasan singkat mengapa dipilih.
- Selalu tampilkan ringkasan portofolio: equity, cash, exposure, realized/unrealized PnL.
- Selalu daftar aset yang SEDANG dipegang (simbol, lot, entry, mark, unrealized, TP, SL) jika ada.
- Jika ada exit TP/SL hari ini, sebutkan dan dampak ke saldo.
- JANGAN menyarankan beli/jual di luar data sinyal yang diberikan.
- JANGAN klaim profit, edge terbukti, atau production ready 100%.
- JANGAN perintah eksekusi live. Tegaskan ini simulasi paper bila relevan.
- Jika tidak ada sinyal, jelaskan status run dan kondisi paper portfolio.
- Jika halted/error, jelaskan penyebab dan dampak.
- Akhiri dengan satu baris: \"Paper simulation — NO LIVE EXECUTION\"
- Jangan gunakan markdown tebal berlebihan; teks polos untuk Telegram.
"""


def _api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def _model() -> str:
    return (os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip()


def gemini_configured() -> bool:
    return bool(_api_key())


def _fallback(kind: str, payload: dict[str, Any]) -> str:
    """Deterministic template if Gemini unavailable."""
    td = payload.get("trading_date", "")
    mode = payload.get("mode", "")
    status = payload.get("status", kind)
    if kind == "signals":
        lines = ["📊 IDX PORTFOLIO DASHBOARD", f"Tanggal: {td} | Mode: {mode}", ""]
        top = payload.get("top_signal") or ((payload.get("signals") or [None])[0])
        if top:
            conf = top.get("confidence")
            conf_s = f"{float(conf)*100:.0f}%" if conf is not None else "-"
            lines += [
                "🎯 SINYAL TOP-1 (BUY)",
                f"  {top.get('symbol')} @ Rp{float(top.get('price') or top.get('entry_price') or 0):,.0f}",
                f"  Lot: {top.get('lots', '-')} | Total: Rp{float(top.get('notional') or top.get('total_cost') or 0):,.0f}",
                f"  TP: Rp{float(top.get('tp') or 0):,.0f} | SL: Rp{float(top.get('sl') or 0):,.0f}",
                f"  Conf: {conf_s}",
                "",
            ]
        pf = payload.get("portfolio") or {}
        lines += [
            "💼 PORTFOLIO",
            f"  Equity: Rp{float(pf.get('equity') or 0):,.0f}",
            f"  Cash: Rp{float(pf.get('cash') or 0):,.0f}",
            f"  Exposure: {float(pf.get('exposure') or 0)*100:.1f}%",
            "",
        ]
        opens = pf.get("open_positions") or {}
        if opens:
            lines.append("📦 POSISI TERBUKA")
            for sym, p in list(opens.items())[:10]:
                if isinstance(p, dict):
                    lines.append(
                        f"  {sym} {float(p.get('lots') or 0):.0f} lot | "
                        f"entry Rp{float(p.get('avg_entry') or 0):,.0f} | "
                        f"uPnL Rp{float(p.get('unrealized_pnl') or 0):,.0f}"
                    )
            lines.append("")
        lines.append("Paper simulation — NO LIVE EXECUTION")
        return "\n".join(lines)
    if kind == "no_signal":
        lines = [
            "IDX — TIDAK ADA SINYAL",
            f"Tanggal: {td} | Mode: {mode}",
            f"Status: {status}",
            "",
            "Tidak ada kandidat BUY yang lolos filter hari ini.",
            "Paper portfolio tidak menambah posisi baru dari sinyal hari ini.",
        ]
        pf = payload.get("portfolio") or {}
        if pf.get("equity") is not None:
            lines.append(f"Equity paper: Rp{float(pf['equity']):,.0f}")
        if payload.get("freshness"):
            lines.append(f"Freshness: {payload.get('freshness')}")
        if payload.get("data_source"):
            lines.append(f"Data: {payload.get('data_source')}")
        lines += ["", "Paper simulation — NO LIVE EXECUTION"]
        return "\n".join(lines)
    lines = [
        "IDX — STATUS OPERASIONAL",
        f"Tanggal: {td} | Mode: {mode}",
        f"Status: {status}",
        str(payload.get("reason") or payload.get("details") or ""),
        "",
        "Paper simulation — NO LIVE EXECUTION",
    ]
    return "\n".join(lines)


def _call_gemini(user_prompt: str, *, timeout: float = 45.0) -> str:
    key = _api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")
    model = _model()
    url = f"{API_BASE}/models/{model}:generateContent"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_RULES}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 700,
        },
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, params={"key": key}, json=body)
        r.raise_for_status()
        data = r.json()
    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"gemini_empty_candidates: {data.get('promptFeedback')}")
    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    text = "".join(str(p.get("text") or "") for p in parts).strip()
    if not text:
        raise RuntimeError("gemini_empty_text")
    if len(text) > 3500:
        text = text[:3490] + "…"
    return text


def narrate(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    meta = {
        "narrator": "gemini",
        "model": _model(),
        "fallback": False,
        "kind": kind,
        "configured": gemini_configured(),
    }
    facts = json.dumps(payload, ensure_ascii=False, default=str)[:14000]
    prompts = {
        "signals": (
            "Buat pesan Telegram berbentuk DASHBOARD PORTOFOLIO IDX.\n"
            "Wajib: (1) Sinyal TOP-1 saja — simbol, harga, lot, total pembelian, TP, SL, "
            "dan narasi singkat MENGAPA sinyal ini dikirim.\n"
            "(2) Ringkasan equity/cash/exposure/PnL.\n"
            "(3) Daftar posisi terbuka yang sedang dipegang (jika ada).\n"
            "(4) Exit TP/SL hari ini jika ada, beserta dampak saldo.\n"
            "Bahasa Indonesia, ringkas, teks polos.\n\n"
            f"FACTS_JSON:\n{facts}"
        ),
        "no_signal": (
            "Tidak ada sinyal trading hari ini. Jelaskan ke user mengapa tidak ada sinyal "
            "(mode, scan, data, freshness, filter) dan kondisi paper portfolio. "
            "Tenangkan bahwa ini normal dan sistem tetap signal-only paper.\n\n"
            f"FACTS_JSON:\n{facts}"
        ),
        "halt": (
            "Sistem IDX dihentikan/terblokir untuk siklus ini. Jelaskan reason dan details "
            "dengan jelas, dampak ke sinyal dan paper portfolio.\n\n"
            f"FACTS_JSON:\n{facts}"
        ),
        "status": (
            "Buat update status operasional IDX untuk Telegram dari facts berikut.\n\n"
            f"FACTS_JSON:\n{facts}"
        ),
    }
    prompt = prompts.get(kind, prompts["status"])
    if not gemini_configured():
        meta["fallback"] = True
        meta["narrator"] = "template_fallback"
        meta["reason"] = "GEMINI_API_KEY_missing"
        return {"text": _fallback(kind, payload), **meta}
    try:
        text = _call_gemini(prompt)
        return {"text": text, **meta}
    except Exception as e:
        meta["fallback"] = True
        meta["narrator"] = "template_fallback"
        meta["reason"] = f"{type(e).__name__}: {e}"[:200]
        return {"text": _fallback(kind, payload), **meta}


def narrate_signals(*, trading_date: str, mode: str, signals: list[dict],
                    portfolio: dict, governor: str, dq: str,
                    extra: Optional[dict] = None) -> dict[str, Any]:
    top = signals[0] if signals else None
    payload = {
        "trading_date": trading_date,
        "mode": mode,
        "status": "SIGNALS",
        "top_signal": top,
        "signals": signals[:1],
        "portfolio": portfolio,
        "exits": (extra or {}).get("exits") or [],
        "governor": governor,
        "dq": dq,
        **(extra or {}),
    }
    return narrate("signals", payload)


def narrate_no_signal(*, trading_date: str, mode: str, report: dict) -> dict[str, Any]:
    payload = {
        "trading_date": trading_date,
        "mode": mode,
        "status": report.get("status", "NO_SIGNAL"),
        "signals_generated": report.get("signals_generated", 0),
        "signals_scanned": report.get("signals_scanned"),
        "symbols_loaded_count": report.get("symbols_loaded_count"),
        "data_source": report.get("data_source"),
        "freshness": report.get("freshness"),
        "dq_status": report.get("dq_status"),
        "portfolio": report.get("paper_portfolio") or {},
        "exits": report.get("exits_today") or [],
        "governor": report.get("governor_action"),
        "economic_edge": report.get("economic_edge", "UNVERIFIED"),
        "production_ready": report.get("production_ready", False),
    }
    return narrate("no_signal", payload)


def narrate_halt(*, trading_date: str, mode: str, reason: str, details: str,
                 report: Optional[dict] = None) -> dict[str, Any]:
    payload = {
        "trading_date": trading_date,
        "mode": mode,
        "status": (report or {}).get("status", "HALTED"),
        "reason": reason,
        "details": details,
        "data_source": (report or {}).get("data_source"),
        "freshness": (report or {}).get("freshness"),
    }
    return narrate("halt", payload)
