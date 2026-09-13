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
- Bahasa Indonesia, netral, profesional, ringkas (maks ~900 karakter).
- JANGAN menyarankan beli/jual di luar data sinyal yang diberikan.
- JANGAN klaim profit, edge terbukti, atau production ready 100%.
- JANGAN perintah eksekusi live. Tegaskan ini simulasi paper bila relevan.
- Jika tidak ada sinyal, jelaskan status run (mode, data, freshness, portfolio) dengan jelas.
- Jika halted/error, jelaskan penyebab dan dampak (tidak ada sinyal baru).
- Akhiri dengan satu baris: "Paper simulation — NO LIVE EXECUTION"
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
        lines = [
            "IDX DAILY SIGNAL (fallback narration)",
            f"Tanggal: {td} | Mode: {mode}",
            "",
        ]
        for s in payload.get("signals") or []:
            conf = s.get("confidence")
            conf_s = f" conf={float(conf)*100:.0f}%" if conf is not None else ""
            lines.append(f"- {s.get('symbol')} {s.get('side_label', 'BUY')}{conf_s}")
        pf = payload.get("portfolio") or {}
        if pf.get("equity") is not None:
            lines += ["", f"Paper equity: Rp{float(pf['equity']):,.0f}"]
        lines += ["", "Paper simulation — NO LIVE EXECUTION"]
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
            "maxOutputTokens": 512,
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
    """Return {text, narrator, model, fallback}. kind: signals | no_signal | halt | status"""
    meta = {
        "narrator": "gemini",
        "model": _model(),
        "fallback": False,
        "kind": kind,
        "configured": gemini_configured(),
    }
    facts = json.dumps(payload, ensure_ascii=False, default=str)[:12000]
    prompts = {
        "signals": (
            "Narasikan ringkasan sinyal harian IDX berikut untuk Telegram. "
            "Sebutkan tanggal, mode, daftar simbol+sisi+confidence, dan ringkas paper portfolio.\n\n"
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
    payload = {
        "trading_date": trading_date,
        "mode": mode,
        "status": "SIGNALS",
        "signals": signals,
        "portfolio": portfolio,
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
