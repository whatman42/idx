"""Executive summary — reporting layer only; anti-hallucination + fallback."""
from __future__ import annotations

from src.python.reporting.builder import build_cycle_report, build_buy_signal
from src.python.reporting.executive_summary import (
    build_executive_payload,
    deterministic_executive_summary,
    payload_fingerprint,
    should_emit_summary,
    mark_emitted,
    reset_summary_cache,
)
from src.python.llm.executive_summary_gemini import generate_executive_summary
from src.python.reporting.llm_boundary import compose_with_executive_summary


def _empty_report(**kw):
    return build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary={
            "cash": 10_000_000,
            "equity": 10_000_000,
            "realized_pnl": 0,
            "open_positions": {},
            "initial_capital": 10_000_000,
        },
        no_signal_reasons=["Tidak ada saham yang memenuhi seluruh syarat pembelian saat ini."],
        status="NO_SIGNAL",
        **kw,
    )


def test_payload_from_cycle_no_buy():
    r = _empty_report()
    p = build_executive_payload(r)
    assert p["decision"]["action"] == "NO_BUY"
    assert p["portfolio"]["positions"] == 0
    assert p["signals"]["buy"] == 0
    assert p["system"]["live_execution"] is False


def test_deterministic_summary_format():
    r = _empty_report()
    p = build_executive_payload(r)
    text = deterministic_executive_summary(p)
    assert "INTI LAPORAN" in text
    assert "KEPUTUSAN" in text
    assert "PORTOFOLIO" in text
    assert "PERFORMA BOT" in text
    assert "PERLU DIPERHATIKAN" in text
    assert "KESIMPULAN" in text
    assert "tidak memiliki posisi" in text.lower() or "kas" in text.lower()
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text


def test_fingerprint_stable():
    r = _empty_report()
    p = build_executive_payload(r)
    assert payload_fingerprint(p) == payload_fingerprint(p)


def test_fingerprint_changes_on_portfolio():
    r1 = _empty_report()
    r2 = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary={
            "cash": 5_000_000,
            "equity": 10_000_000,
            "realized_pnl": 0,
            "initial_capital": 10_000_000,
            "open_positions": {
                "BBCA": {
                    "avg_entry": 9850,
                    "last_mark": 9900,
                    "qty": 500,
                    "lots": 5,
                    "tp": 10441,
                    "sl": 9555,
                }
            },
        },
    )
    assert payload_fingerprint(build_executive_payload(r1)) != payload_fingerprint(
        build_executive_payload(r2)
    )


def test_generate_without_api_key_uses_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    r = _empty_report()
    p = build_executive_payload(r)
    text, obs = generate_executive_summary(p, use_llm=True)
    assert obs.fallback_used is True
    assert "INTI LAPORAN" in text
    assert obs.source in ("deterministic", "deterministic_fallback")


def test_generate_llm_disabled():
    r = _empty_report()
    p = build_executive_payload(r)
    text, obs = generate_executive_summary(p, use_llm=False)
    assert obs.source == "deterministic"
    assert "PORTOFOLIO" in text


def test_timeout_fallback(monkeypatch):
    r = _empty_report()
    p = build_executive_payload(r)

    def boom(*a, **k):
        raise TimeoutError("timeout")

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("src.python.llm.executive_summary_gemini._call_gemini", boom)
    text, obs = generate_executive_summary(p, use_llm=True)
    assert obs.fallback_used is True
    assert obs.error_category == "timeout"
    assert "INTI LAPORAN" in text


def test_api_failure_fallback(monkeypatch):
    r = _empty_report()
    p = build_executive_payload(r)

    def boom(*a, **k):
        raise RuntimeError("gemini_http_500")

    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr("src.python.llm.executive_summary_gemini._call_gemini", boom)
    text, obs = generate_executive_summary(p, use_llm=True)
    assert obs.fallback_used is True
    assert "api_error" in obs.error_category or "error" in obs.error_category


def test_empty_response_fallback(monkeypatch):
    r = _empty_report()
    p = build_executive_payload(r)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def empty(*a, **k):
        raise RuntimeError("gemini_empty_text")

    monkeypatch.setattr("src.python.llm.executive_summary_gemini._call_gemini", empty)
    text, obs = generate_executive_summary(p, use_llm=True)
    assert obs.fallback_used is True
    assert "INTI" in text


def test_malformed_hallucinated_buy_rejected(monkeypatch):
    r = _empty_report()
    p = build_executive_payload(r)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

    def bad(*a, **k):
        return (
            "🧠 INTI LAPORAN\nBot siap.\n"
            "📌 KEPUTUSAN\nREKOMENDASI BUY BBCA sekarang.\n"
            "💰 PORTOFOLIO\nEkuitas bagus.\n"
            "📈 PERFORMA BOT\nMenguntungkan.\n"
            "⚠️ PERLU DIPERHATIKAN\nTidak ada.\n"
            "🎯 KESIMPULAN\nBeli sekarang."
        )

    monkeypatch.setattr("src.python.llm.executive_summary_gemini._call_gemini", bad)
    text, obs = generate_executive_summary(p, use_llm=True)
    assert obs.fallback_used is True or obs.validation_ok is False
    assert "REKOMENDASI BUY BBCA sekarang" not in text


def test_valid_llm_response_accepted(monkeypatch):
    r = _empty_report()
    p = build_executive_payload(r)
    good = deterministic_executive_summary(p)
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(
        "src.python.llm.executive_summary_gemini._call_gemini",
        lambda *a, **k: good,
    )
    text, obs = generate_executive_summary(p, use_llm=True)
    assert obs.source == "llm"
    assert obs.validation_ok is True
    assert text == good


def test_insufficient_performance_sample_language():
    r = _empty_report()
    p = build_executive_payload(r, performance={"trades": 1, "win_rate": 1.0})
    text = deterministic_executive_summary(p)
    assert "sampel" in text.lower() or "belum" in text.lower() or "trades" in text.lower()


def test_duplicate_suppression():
    reset_summary_cache()
    fp = "abc123"
    assert should_emit_summary(fp) is True
    mark_emitted(fp)
    assert should_emit_summary(fp) is False
    assert should_emit_summary("other") is True
    reset_summary_cache()


def test_compose_with_executive_keeps_dashboard():
    r = _empty_report()
    p = build_executive_payload(r)
    exec_text = deterministic_executive_summary(p)
    text, src = compose_with_executive_summary(r, executive_text=exec_text, executive_enabled=True)
    assert "PORTOFOLIO SAHAM IDX" in text
    assert "INTI LAPORAN" in text
    assert src == "deterministic+executive"
    assert "SIGNAL ONLY" in text or "NO LIVE EXECUTION" in text


def test_telegram_length_reasonable():
    r = _empty_report()
    p = build_executive_payload(r)
    text = deterministic_executive_summary(p)
    assert len(text) < 2000
    assert len(text.split()) < 220


def test_buy_signal_payload():
    sig = build_buy_signal(
        signal_id="s1",
        timestamp="2026-09-15",
        symbol="BBCA",
        entry_reference=9850,
        stop_loss=9555,
        tp1=10150,
        tp2=10441,
        shares=500,
        equity=10_120_000,
        confidence=72,
        confidence_method="sma20",
        explanation=["Ranking #1"],
    )
    r = build_cycle_report(
        trading_date="2026-09-15",
        mode="PAPER",
        pf_summary={
            "cash": 5_195_000,
            "equity": 10_145_000,
            "realized_pnl": 0,
            "initial_capital": 10_000_000,
            "open_positions": {
                "BBCA": {
                    "avg_entry": 9850,
                    "last_mark": 9900,
                    "qty": 500,
                    "lots": 5,
                    "tp": 10441,
                    "sl": 9555,
                }
            },
        },
        signal=sig,
    )
    p = build_executive_payload(r)
    assert p["decision"]["action"] == "BUY"
    assert p["decision"]["symbol"] == "BBCA"
    text = deterministic_executive_summary(p)
    assert "BUY" in text
    assert "BBCA" in text
