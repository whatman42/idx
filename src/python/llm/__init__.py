"""Advisory LLM helpers — never change signals, portfolio, or production pointer.

Executive summary (Gemini Flash-Lite) is interpretation-only.
Trading decisions remain deterministic / system-controlled.
"""
from src.python.llm.executive_summary_gemini import generate_executive_summary, gemini_configured

__all__ = ["generate_executive_summary", "gemini_configured"]
