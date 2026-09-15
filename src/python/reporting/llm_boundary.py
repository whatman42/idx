"""LLM boundary — validation + safe composition.

Deterministic dashboard is always the source of numbers.
LLM may only supply an executive interpretation section.
"""
from __future__ import annotations

import re
from typing import Optional

from src.python.reporting.composer import DeterministicComposer
from src.python.reporting.models import CycleReport
from src.python.reporting.validation import validate_telegram_payload


class LLMMutationError(Exception):
    def __init__(self, reasons: list[str]):
        self.reasons = list(reasons)
        super().__init__("; ".join(self.reasons))


def validate_llm_output(text: str, report: CycleReport) -> list[str]:
    """Detect decision/symbol/id/numeric mutations and hallucinated facts."""
    errs: list[str] = []
    if not text or not text.strip():
        return ["llm_empty_output"]
    upper = text.upper()

    if report.signal and report.signal.decision == "NO_SIGNAL":
        if re.search(r"(DECISION:\s*BUY|REKOMENDASI\s+BUY|SARAN\s+BUY|HARUS\s+BELI|\bBUY\s+[A-Z]{3,6}\b)", upper):
            if "TIDAK ADA" not in upper and "NO_SIGNAL" not in upper and "NO SIGNAL" not in upper:
                errs.append("llm_mutated_no_signal_to_buy")
        if re.search(r"(DECISION:\s*SELL|REKOMENDASI\s+SELL|SARAN\s+SELL|HARUS\s+JUAL)", upper):
            errs.append("llm_mutated_no_signal_to_sell")
    if report.signal and report.signal.decision == "BUY":
        if re.search(r"🎯\s*SELL|DECISION:\s*SELL", upper):
            errs.append("llm_mutated_buy_to_sell")
    if report.signal and report.signal.decision == "SELL":
        if re.search(r"🎯\s*BUY|DECISION:\s*BUY", upper):
            errs.append("llm_mutated_sell_to_buy")

    sig = report.signal
    if sig and sig.signal_id and sig.decision in ("BUY", "SELL"):
        if sig.signal_id not in text and "SignalID" in text:
            errs.append("llm_signal_id_mismatch")
        if sig.symbol and sig.symbol not in text:
            errs.append("llm_missing_symbol")

    if sig and sig.lots >= 5 and sig.position_value >= 1_000_000:
        wrong = "492.500"
        right_compact = str(int(sig.position_value))
        if wrong in text.replace(",", ".") and right_compact not in text.replace(".", "").replace(",", ""):
            errs.append("llm_numeric_mutation_position_value")

    if "NO LIVE EXECUTION" not in text and "SIGNAL ONLY" not in text:
        errs.append("llm_removed_risk_warning")

    errs.extend(validate_telegram_payload(text, report))
    return errs


def safe_compose(
    report: CycleReport,
    *,
    llm_text: Optional[str] = None,
    llm_enabled: bool = False,
) -> tuple[str, str]:
    """Legacy path: optional full-message LLM with fallback to deterministic."""
    det = DeterministicComposer().compose(report)
    if not llm_enabled or not llm_text:
        return det, "deterministic"
    problems = validate_llm_output(llm_text, report)
    if problems:
        return det, "deterministic_fallback"
    return llm_text, "llm"


def compose_with_executive_summary(
    report: CycleReport,
    *,
    executive_text: Optional[str] = None,
    executive_enabled: bool = True,
) -> tuple[str, str]:
    """Always render deterministic dashboard; optionally append executive summary."""
    det = DeterministicComposer().compose(report)
    if not executive_enabled or not executive_text or not executive_text.strip():
        return det, "deterministic"
    body = executive_text.strip()
    combined = (
        det
        + "\n\n──────────────────────────────\n"
        + "🧠 RINGKASAN EKSEKUTIF (interpretasi, bukan keputusan trading)\n\n"
        + body
    )
    return combined, "deterministic+executive"
