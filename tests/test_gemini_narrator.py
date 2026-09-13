from src.python.llm.gemini_narrator import narrate_no_signal, narrate_signals, _fallback

def test_fallback_no_signal_mentions_no_signal():
    text = _fallback("no_signal", {
        "trading_date": "2026-09-13",
        "mode": "PAPER",
        "status": "NO_SIGNAL",
        "portfolio": {"equity": 10_000_000},
    })
    assert "TIDAK ADA SINYAL" in text or "sinyal" in text.lower()
    assert "NO LIVE EXECUTION" in text

def test_narrate_no_signal_without_key_uses_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    out = narrate_no_signal(
        trading_date="2026-09-13",
        mode="OPERATIONAL",
        report={"status": "NO_SIGNAL", "signals_generated": 0, "paper_portfolio": {"equity": 1e7}},
    )
    assert out["fallback"] is True
    assert "NO LIVE EXECUTION" in out["text"]

def test_narrate_signals_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    out = narrate_signals(
        trading_date="2026-09-13",
        mode="PAPER",
        signals=[{"symbol": "BBCA", "side_label": "BUY", "confidence": 0.6}],
        portfolio={"equity": 1e7},
        governor="ALLOW_PAPER_SIGNAL",
        dq="PASS",
    )
    assert "BBCA" in out["text"]
    assert out["fallback"] is True
