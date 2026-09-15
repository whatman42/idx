"""Gemini Flash-Lite executive summary — interpretation only, never trading decisions."""
from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx

from src.python.reporting.executive_summary import (
    ExecutiveObservability,
    deterministic_executive_summary,
    payload_fingerprint,
    validate_executive_text,
)

DEFAULT_MODEL = "gemini-3.5-flash-lite"
API_BASE = "https://generativelanguage.googleapis.com/v1beta"

SYSTEM_PROMPT = """Kamu adalah lapisan INTERPRETASI laporan sistem trading IDX (paper / SIGNAL ONLY).

ATURAN MUTLAK:
1. Hanya gunakan data JSON yang diberikan. Jangan menambah angka, alasan, atau fakta di luar data.
2. JANGAN menentukan BUY/SELL/HOLD. JANGAN mengubah sinyal, confidence, TP, SL, sizing, atau risk.
3. JANGAN merekomendasikan transaksi baru. JANGAN mengklaim order live.
4. JANGAN mengklaim sistem "bagus", "aman", "optimal", atau "menguntungkan" tanpa bukti di data.
5. Jika data tidak cukup, tulis: "Data tidak cukup untuk menilai …".
6. Jika field konflik, sebutkan ANOMALI DATA; jangan diam-diam memilih satu nilai.
7. Bedakan performa bot vs pergerakan pasar. Jangan puji bot hanya karena harga naik.
8. Bahasa Indonesia, netral, objektif. Maksimal ~160 kata. Telegram plain text.
9. Ikuti format section tepat seperti ini:

🧠 INTI LAPORAN
[2–4 kalimat]

📌 KEPUTUSAN
[keputusan sistem + alasan dari data]

💰 PORTOFOLIO
[equity, cash, exposure, posisi, return jika ada]

📈 PERFORMA BOT
[metrik yang tersedia; jika tidak ada transaksi: katakan belum dapat dinilai]

⚠️ PERLU DIPERHATIKAN
[anomali/risiko/DQ; atau "Tidak ada anomali material yang dilaporkan dari data yang tersedia."]

🎯 KESIMPULAN
[1–2 kalimat objektif + sebut SIGNAL ONLY / NO LIVE EXECUTION jika system.signal_only atau live_execution=false]
"""


def _api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def _model() -> str:
    return (os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip()


def gemini_configured() -> bool:
    return bool(_api_key())


def _call_gemini(user_prompt: str, *, timeout: float = 30.0) -> str:
    key = _api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY_missing")
    model = _model()
    url = f"{API_BASE}/models/{model}:generateContent?key={key}"
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 512,
        },
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, json=body)
        if resp.status_code >= 400:
            raise RuntimeError(f"gemini_http_{resp.status_code}")
        data = resp.json()
    cands = data.get("candidates") or []
    if not cands:
        raise RuntimeError(f"gemini_empty_candidates:{data.get('promptFeedback')}")
    parts = ((cands[0].get("content") or {}).get("parts")) or []
    text = "".join(p.get("text") or "" for p in parts).strip()
    if not text:
        raise RuntimeError("gemini_empty_text")
    return text


def generate_executive_summary(
    payload: dict[str, Any],
    *,
    use_llm: bool = True,
    timeout: float = 30.0,
) -> tuple[str, ExecutiveObservability]:
    """Return (text, observability). Always returns usable text (LLM or deterministic fallback)."""
    obs = ExecutiveObservability(
        request_ts=time.time(),
        model=_model() if use_llm else "deterministic",
        input_fingerprint=payload_fingerprint(payload),
    )
    fallback = deterministic_executive_summary(payload)

    if not use_llm or not gemini_configured():
        obs.success = True
        obs.validation_ok = True
        obs.fallback_used = True
        obs.source = "deterministic"
        obs.output_length = len(fallback)
        obs.error_category = "llm_disabled_or_unconfigured" if use_llm else "llm_disabled"
        return fallback, obs

    t0 = time.perf_counter()
    try:
        user = (
            "Buat executive summary dari data sistem berikut (JSON). "
            "Jangan menambah fakta di luar JSON.\n\n"
            + json.dumps(payload, ensure_ascii=False, default=str)
        )
        text = _call_gemini(user, timeout=timeout)
        obs.latency_sec = time.perf_counter() - t0
        obs.success = True
        problems = validate_executive_text(text, payload)
        obs.validation_errors = problems
        if problems:
            obs.validation_ok = False
            obs.fallback_used = True
            obs.source = "deterministic_fallback"
            obs.output_length = len(fallback)
            obs.error_category = "validation_failed"
            return fallback, obs
        obs.validation_ok = True
        obs.source = "llm"
        obs.output_length = len(text)
        return text, obs
    except Exception as e:
        obs.latency_sec = time.perf_counter() - t0
        obs.success = False
        obs.fallback_used = True
        obs.source = "deterministic_fallback"
        obs.output_length = len(fallback)
        name = type(e).__name__
        msg = str(e)
        if "timeout" in msg.lower() or name == "TimeoutException":
            obs.error_category = "timeout"
        elif "http_429" in msg or "rate" in msg.lower():
            obs.error_category = "rate_limit"
        elif "GEMINI_API_KEY" in msg:
            obs.error_category = "auth_missing"
        elif "http_" in msg:
            obs.error_category = "api_error"
        elif "empty" in msg.lower():
            obs.error_category = "empty_response"
        else:
            obs.error_category = f"error:{name}"
        return fallback, obs
