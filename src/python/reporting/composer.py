"""Deterministic Telegram message composer — renders structured report only, no recompute."""
from __future__ import annotations

from typing import Optional

from src.python.reporting.models import CycleReport, ExitReport, OpenPositionView, PortfolioSnapshot, SignalReport


def _rp(x: float | int | None) -> str:
    if x is None:
        return "-"
    try:
        return f"Rp{float(x):,.0f}".replace(",", ".")
    except Exception:
        return "-"


def _num(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "-"
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return "-"


class DeterministicComposer:
    """Pure template renderer. All numbers come from CycleReport; no financial math here."""

    def compose(self, report: CycleReport) -> str:
        if not report.integrity_ok:
            return self._integrity_failure(report)
        if report.signal and report.signal.decision in ("BUY", "SELL"):
            return self._signal_message(report)
        return self._no_signal_message(report)

    def _integrity_failure(self, report: CycleReport) -> str:
        lines = [
            "📊 IDX SIGNAL — DATA INTEGRITY FAILURE",
            f"Tanggal: {report.trading_date} | Mode: {report.mode}",
            "",
            "Report tidak dikirim sebagai sinyal valid karena gagal reconciliation/validation.",
            "Errors:",
        ]
        for e in (report.integrity_errors or [])[:12]:
            lines.append(f"  - {e}")
        lines += ["", "⚠️ SIGNAL ONLY", "Paper simulation — NO LIVE EXECUTION"]
        return "\n".join(lines)

    def _signal_message(self, report: CycleReport) -> str:
        sig = report.signal
        assert sig is not None
        lines = [
            "📊 IDX SIGNAL — SIGNAL ONLY",
            f"Tanggal: {report.trading_date}",
            f"Timeframe: {sig.timeframe}",
            f"Regime: {sig.market_regime}",
            f"Mode: {report.mode}",
            "",
            f"🎯 {sig.decision} — {sig.symbol}",
            "",
            f"Entry: {_rp(sig.entry_reference)}",
        ]
        if sig.entry_low > 0 and sig.entry_high > 0:
            lines.append(f"Range: {_rp(sig.entry_low)}–{_rp(sig.entry_high)}")
        lines.append(f"SL: {_rp(sig.stop_loss)}")
        if sig.tp1 > 0:
            lines.append(f"TP1: {_rp(sig.tp1)}")
        if sig.tp2 > 0:
            lines.append(f"TP2: {_rp(sig.tp2)}")
        lines.append("")
        if sig.rr_tp1 is not None:
            lines.append(f"RR TP1: {_num(sig.rr_tp1)}")
        if sig.rr_tp2 is not None:
            lines.append(f"RR TP2: {_num(sig.rr_tp2)}")
        lines += [
            "",
            "Position:",
            f"{_num(sig.lots, 0)} lot / {_num(sig.shares, 0)} shares",
            f"Value: {_rp(sig.position_value)}",
            f"Allocation: {_num(sig.allocation_pct)}%",
            f"Risk: {_rp(sig.risk_amount)}",
            f"Risk %: {_num(sig.risk_pct)}%",
            "",
            "Confidence:",
            f"Model confidence: {_num(sig.confidence, 0)}/100",
            f"Method: {sig.confidence_method}",
            f"Model: {sig.model_version or report.model_version or '-'}",
            f"Features: {sig.feature_version or '-'}",
            "",
            "Why:",
        ]
        why = sig.explanation_context or sig.technical_factors or ["Data tidak tersedia"]
        for w in why[:8]:
            lines.append(f"• {w}")
        lines += ["", "Management:"]
        for m in (sig.management or ["Not configured"])[:6]:
            lines.append(f"• {m}")
        lines.append("")
        lines.extend(self._portfolio_block(report.portfolio))
        lines.append("")
        lines.extend(self._exits_block(report.exits))
        lines += [
            "",
            f"SignalID: {sig.signal_id}",
            f"Governor: {report.governor_action or '-'}",
            f"DQ: {report.dq_status or '-'}",
            "",
            "⚠️ SIGNAL ONLY — bukan ajakan beli/jual",
            "Paper simulation — NO LIVE EXECUTION",
        ]
        return "\n".join(lines)

    def _no_signal_message(self, report: CycleReport) -> str:
        lines = [
            "📊 IDX SIGNAL — NO SIGNAL",
            f"Tanggal: {report.trading_date}",
            f"Mode: {report.mode}",
            "",
            "Decision: NO_SIGNAL",
            "",
            "Reason:",
        ]
        reasons = report.no_signal_reasons or ["Tidak ada kandidat yang lolos filter hari ini."]
        for r in reasons[:8]:
            lines.append(f"• {r}")
        lines += ["", f"Risk gate: {report.risk_gate}", f"Model: {report.model_version or '-'}", ""]
        lines.extend(self._portfolio_block(report.portfolio))
        lines.append("")
        lines.extend(self._exits_block(report.exits))
        lines += ["", "⚠️ SIGNAL ONLY — bukan ajakan beli/jual", "Paper simulation — NO LIVE EXECUTION"]
        return "\n".join(lines)

    def _portfolio_block(self, pf: Optional[PortfolioSnapshot]) -> list[str]:
        if not pf:
            return ["💼 PORTFOLIO", "Data tidak tersedia"]
        lines = [
            "💼 PORTFOLIO",
            f"Equity: {_rp(pf.equity)}",
            f"Cash: {_rp(pf.cash)}",
            f"Exposure: {_num(pf.exposure_pct)}%",
            f"Realized: {_rp(pf.realized_pnl)}",
            f"Unrealized: {_rp(pf.unrealized_pnl)}",
        ]
        if pf.open_positions:
            lines += ["", "📦 OPEN POSITIONS"]
            for p in pf.open_positions[:15]:
                lines.append(self._position_line(p))
        return lines

    def _position_line(self, p: OpenPositionView) -> str:
        return (
            f"{p.symbol}  {_num(p.lots, 0)} lot / {_num(p.shares, 0)} shares | "
            f"entry {_rp(p.entry_price)} | mark {_rp(p.mark_price)} | "
            f"uPnL {_rp(p.unrealized_pnl)} | TP2 {_rp(p.tp2)} | SL {_rp(p.stop_loss)}"
        )

    def _exits_block(self, exits: list[ExitReport]) -> list[str]:
        if not exits:
            return []
        lines = ["✅ EXIT"]
        for e in exits[:10]:
            lines.append(
                f"{e.symbol}  entry {_rp(e.entry_price)} exit {_rp(e.exit_price)} | "
                f"{_num(e.lots, 0)} lot / {_num(e.shares, 0)} shares | "
                f"PnL {_rp(e.realized_pnl)} ({_num(e.pnl_pct)}%) | "
                f"{e.duration} | {e.exit_reason}"
            )
        return lines


def compose_telegram_message(report: CycleReport) -> str:
    return DeterministicComposer().compose(report)
