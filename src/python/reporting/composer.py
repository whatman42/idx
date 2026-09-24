"""Deterministic Telegram message composer — beginner-friendly UX, audit details below.

All numbers come from CycleReport only. No financial recompute. No invented reasons.
"""
from __future__ import annotations

from typing import Optional

from src.python.reporting.models import CycleReport, ExitReport, OpenPositionView, PortfolioSnapshot, SignalReport

_SEP = "══════════════════════════════"


def _entry_date(ts: Optional[str]) -> str:
    """Prefer calendar date; hide synthetic midnight if no intraday."""
    if not ts:
        return "-"
    s = str(ts).strip()
    if "T00:00:00" in s or s.endswith(" 00:00:00"):
        return s[:10]
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        if "T" in s and not s[11:19].startswith("00:00:00"):
            return s[:19].replace("T", " ")
        return s[:10]
    return s


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


def _pct(x: float | None, digits: int = 2) -> str:
    if x is None:
        return "-"
    try:
        return f"{float(x):.{digits}f}%"
    except Exception:
        return "-"


def _mode_label(report: CycleReport) -> str:
    mode = (report.mode or "-").upper()
    if report.live_execution:
        return f"Mode: {mode} • LIVE"
    if mode in ("PAPER", "TEST", "OPERATIONAL") or report.signal_only:
        return f"Mode: {mode} • PAPER TRADING — INSTANT SIMULATION"
    return f"Mode: {mode}"


def _system_status(report: CycleReport) -> str:
    status = (report.status or "").upper()
    gate = (report.risk_gate or "").upper()
    if not report.integrity_ok:
        return "🔴 BLOCKED"
    if "BLOCK" in status or gate in ("BLOCKED", "BLOCK", "FAIL", "FAILED"):
        return "🔴 BLOCKED"
    if "HALT" in status or "WARN" in status or (report.dq_status or "").upper() in ("FAIL", "WARN"):
        return "🟡 WARNING"
    if gate and gate not in ("PASS", "OK", ""):
        return "🟡 WARNING"
    return "🟢 NORMAL"


def _decision_label(report: CycleReport) -> str:
    sig = report.signal
    if not report.integrity_ok:
        return "🔴 DATA TIDAK VALID"
    if sig and sig.decision == "BUY":
        return f"🟢 SINYAL BUY — {sig.symbol}"
    if sig and sig.decision == "SELL":
        return f"🔴 SINYAL SELL — {sig.symbol}"
    if sig and sig.decision == "NO_SIGNAL":
        return "🟡 TIDAK ADA PEMBELIAN"
    if report.exits:
        return "ℹ️ ADA PENJUALAN / EXIT"
    return "🟡 TIDAK ADA PEMBELIAN"


class DeterministicComposer:
    """Pure template renderer. Numbers only from CycleReport."""

    def compose(self, report: CycleReport) -> str:
        if not report.integrity_ok:
            return self._integrity_failure(report)
        body = self._dashboard(report)
        return body + "\n" + "\n".join(self._footer(report))

    def compose_body(self, report: CycleReport) -> str:
        if not report.integrity_ok:
            return self._integrity_failure(report)
        return self._dashboard(report)

    def _integrity_failure(self, report: CycleReport) -> str:
        lines = [
            "📊 PORTOFOLIO SAHAM IDX",
            f"🗓️ {report.trading_date}",
            _mode_label(report),
            "",
            _SEP,
            "🎯 KEPUTUSAN BOT",
            "",
            "🔴 DATA TIDAK VALID",
            "",
            "Laporan tidak dikirim sebagai sinyal valid karena data tidak konsisten.",
            "",
            "➡️ Tindakan:",
            "Jangan menindaklanjuti pesan ini sebagai rekomendasi beli/jual.",
            "",
            _SEP,
            "🔎 STATUS SISTEM",
            "",
            "Status sistem          : 🔴 BLOCKED",
            "",
            "Kesalahan (audit):",
        ]
        for e in (report.integrity_errors or [])[:12]:
            lines.append(f"  • {e}")
        lines += self._footer(report)
        return "\n".join(lines)

    def _dashboard(self, report: CycleReport) -> str:
        lines: list[str] = []
        lines.extend(self._header(report))
        lines.append("")
        lines.extend(self._funds_block(report.portfolio))
        lines.append("")
        lines.extend(self._decision_block(report))
        lines.append("")
        lines.extend(self._positions_block(report.portfolio))
        lines.append("")
        lines.extend(self._exits_section(report.exits))
        lines.append("")
        lines.extend(self._signal_section(report))
        lines.append("")
        lines.extend(self._system_block(report))
        return "\n".join(lines)

    def _header(self, report: CycleReport) -> list[str]:
        return [
            "📊 PORTOFOLIO SAHAM IDX",
            f"🗓️ {report.trading_date}",
            _mode_label(report),
            "",
            _SEP,
        ]

    def _funds_block(self, pf: Optional[PortfolioSnapshot]) -> list[str]:
        lines = ["💰 KONDISI DANA", ""]
        if not pf:
            lines += [
                "Modal Awal       : Tidak tersedia",
                "Total Equity     : Tidak tersedia",
                "Dana Tunai       : Tidak tersedia",
                "Dana Terpakai    : -",
                "Total P/L        : -",
                "",
                "📌 Saham Dimiliki : Tidak tersedia",
                "",
                _SEP,
            ]
            return lines
        base = float(pf.initial_capital or 0)
        equity = float(pf.equity or 0)
        total_pnl = equity - base if base else 0.0
        realized = float(pf.realized_pnl or 0)
        unrealized = float(pf.unrealized_pnl or 0)
        pnl_pct = (total_pnl / base * 100.0) if base > 0 else None
        n_pos = len(pf.open_positions or [])
        lines += [
            f"Modal Awal       : {_rp(pf.initial_capital)}" if pf.initial_capital else "Modal Awal       : -",
            f"Total Equity     : {_rp(pf.equity)}",
            f"Dana Tunai       : {_rp(pf.cash)}",
            f"Dana Terpakai    : {_pct(pf.exposure_pct)}",
            f"Total P/L        : {_rp(total_pnl)}"
            + (f" ({_pct(pnl_pct)})" if pnl_pct is not None else ""),
            f"  Realized P/L   : {_rp(realized)}",
            f"  Unrealized P/L : {_rp(unrealized)}",
            f"  (Total P/L = Equity − Modal; fees tercermin di equity)",
            "",
            f"📌 Saham Dimiliki : {n_pos} posisi" if n_pos else "📌 Saham Dimiliki : Tidak ada",
            "",
            _SEP,
        ]
        return lines

    def _decision_block(self, report: CycleReport) -> list[str]:
        label = _decision_label(report)
        lines = ["🎯 KEPUTUSAN BOT", "", label, ""]
        sig = report.signal
        if sig and sig.decision == "BUY":
            why = (sig.explanation_context or sig.technical_factors or [])[:3]
            if why:
                for w in why:
                    lines.append(str(w))
            else:
                lines.append("Sistem menghasilkan sinyal BUY yang lolos filter.")
            lines.append("")
            lines.append("➡️ Tindakan:")
            fill = getattr(sig, "fill_status", "") or ""
            if fill in ("PAPER_FILLED", "FULL_FILL", "FILLED", "FULL FILL"):
                lines.append("📥 PAPER FILL")
                lines.append("Status     : PAPER_FILLED")
                if sig.lots or sig.shares:
                    lines.append(f"Jumlah     : {_num(sig.lots, 0)} lot / {_num(sig.shares, 0)} lembar")
                if sig.entry_reference:
                    lines.append(f"Harga Fill : {_rp(sig.entry_reference)}")
                lines.append("Simulasi transaksi berhasil dicatat.")
                pf = report.portfolio
                if pf and pf.cash is not None:
                    lines.append(f"💰 Cash setelah transaksi: {_rp(pf.cash)}")
            elif fill:
                lines.append(f"Status simulasi: {fill}")
            lines.append("Broker: tidak dikirim — NO LIVE EXECUTION.")
            lines.append(f"📦 ASET PORTOFOLIO: {sig.symbol} tercatat di paper portfolio.")
        elif sig and sig.decision == "SELL":
            why = (sig.explanation_context or [])[:3]
            for w in why:
                lines.append(str(w))
            if not why:
                lines.append("Sistem mencatat keputusan jual berdasarkan state aktual.")
            lines.append("")
            lines.append("➡️ Tindakan:")
            lines.append("Broker: tidak dikirim — NO LIVE EXECUTION.")
            lines.append(f"Catat sinyal SELL {sig.symbol} untuk audit — bukan order live.")
        else:
            reasons = list(report.no_signal_reasons or [])
            if reasons:
                for r in reasons[:5]:
                    lines.append(str(r))
            else:
                lines.append("Tidak ada saham yang memenuhi semua syarat untuk dibeli saat ini.")
            lines.append("")
            lines.append("➡️ Tindakan:")
            pf = report.portfolio
            if pf and float(pf.exposure_pct or 0) <= 0.01 and not (pf.open_positions or []):
                lines.append("Pertahankan dana dalam bentuk kas.")
            elif pf and (pf.open_positions or []):
                lines.append("Pertahankan posisi yang sudah ada; tidak ada pembelian baru.")
            else:
                lines.append("Tidak ada pembelian baru hari ini.")
        lines += ["", _SEP]
        return lines

    def _positions_block(self, pf: Optional[PortfolioSnapshot]) -> list[str]:
        lines = ["📋 SAHAM YANG DIMILIKI", ""]
        if not pf or not pf.open_positions:
            lines += ["Tidak ada posisi aktif.", "", _SEP]
            return lines
        for p in pf.open_positions[:15]:
            lines.extend(self._position_detail(p))
            lines.append("")
        lines.append(_SEP)
        return lines

    def _position_detail(self, p: OpenPositionView) -> list[str]:
        lots_s = _num(p.lots, 0)
        shares_s = _num(p.shares, 0)
        cost_basis = getattr(p, "cost_basis", None)
        if cost_basis is None and p.entry_price is not None and p.shares is not None:
            try:
                cost_basis = float(p.entry_price) * float(p.shares)
            except Exception:
                cost_basis = None
        market_value = getattr(p, "market_value", None)
        if market_value is None and p.mark_price is not None and p.shares is not None:
            try:
                market_value = float(p.mark_price) * float(p.shares)
            except Exception:
                market_value = None
        return [
            f"• {p.symbol}",
            f"  Jumlah         : {lots_s} lot ({shares_s} lembar)",
            f"  Harga Beli     : {_rp(p.entry_price)}",
            f"  Harga Sekarang : {_rp(p.mark_price)}",
            f"  Modal Posisi   : {_rp(cost_basis)}",
            f"  Nilai Pasar    : {_rp(market_value)}",
            f"  Target Profit  : {_rp(p.tp2) if p.tp2 else (_rp(p.tp1) if p.tp1 else '-')}",
            f"  Batas Rugi     : {_rp(p.stop_loss) if p.stop_loss else '-'}",
            f"  Tanggal Beli   : {_entry_date(p.opened_at)}",
            f"  Unrealized P/L : {_rp(p.unrealized_pnl)}",
        ]

    def _exits_section(self, exits: list[ExitReport]) -> list[str]:
        if not exits:
            return []
        lines = ["✅ TRANSAKSI SELESAI (EXIT)", ""]
        for e in exits[:10]:
            lines.append(f"• {e.symbol}")
            lines.append(f"  Harga Beli / Jual : {_rp(e.entry_price)} → {_rp(e.exit_price)}")
            lines.append(f"  Jumlah       : {_num(e.lots, 0)} lot ({_num(e.shares, 0)} lembar)")
            lines.append(f"  P/L          : {_rp(e.realized_pnl)} ({_pct(e.pnl_pct)})")
            lines.append(f"  Alasan       : {e.exit_reason or '-'}")
            lines.append(f"  Waktu        : {e.timestamp or '-'}")
            lines.append("")
        lines.append(_SEP)
        return lines

    def _signal_section(self, report: CycleReport) -> list[str]:
        lines = ["📡 REKOMENDASI / SINYAL", ""]
        sig = report.signal
        if sig and sig.decision == "BUY":
            lines.append("Rekomendasi utama (data sistem):")
            lines.append("")
            lines.append(f"• {sig.symbol} — SINYAL BUY")
            lines.append(f"  Harga acuan     : {_rp(sig.entry_reference)}")
            if sig.entry_low > 0 and sig.entry_high > 0 and (
                abs(sig.entry_low - sig.entry_reference) > 1e-9
                or abs(sig.entry_high - sig.entry_reference) > 1e-9
            ):
                lines.append(f"  Rentang entry   : {_rp(sig.entry_low)} – {_rp(sig.entry_high)}")
            lines.append(f"  Target Profit   : {_rp(sig.tp2) if sig.tp2 else (_rp(sig.tp1) if sig.tp1 else '-')}")
            if sig.tp1 > 0 and sig.tp2 > 0:
                lines.append(f"  Target 1 / 2    : {_rp(sig.tp1)} / {_rp(sig.tp2)}")
            lines.append(f"  Batas Rugi      : {_rp(sig.stop_loss) if sig.stop_loss else '-'}")
            if sig.lots or sig.shares:
                lines.append(f"  Ukuran posisi   : {_num(sig.lots, 0)} lot / {_num(sig.shares, 0)} lembar")
            if sig.position_value:
                lines.append(f"  Nilai posisi    : {_rp(sig.position_value)}")
            if sig.allocation_pct:
                lines.append(f"  Alokasi         : {_pct(sig.allocation_pct)}")
            if sig.risk_amount:
                lines.append(f"  Risiko (Rp)     : {_rp(sig.risk_amount)} ({_pct(sig.risk_pct)})")
            if sig.rr_tp2 is not None:
                lines.append(f"  Risk:Reward     : 1 : {_num(sig.rr_tp2)}")
            elif sig.rr_tp1 is not None:
                lines.append(f"  Risk:Reward     : 1 : {_num(sig.rr_tp1)}")
            lines.append(f"  Skor Model      : {_num(sig.confidence, 0)}/100")
            lines.append(f"  Metode          : {sig.confidence_method or '-'}")
            lines.append("  Catatan         : skor ranking model, bukan probabilitas naik")
            if sig.explanation_context:
                lines.append("  Alasan (sistem):")
                for w in sig.explanation_context[:5]:
                    lines.append(f"    • {w}")
        elif sig and sig.decision == "SELL":
            lines.append(f"Sinyal jual: {sig.symbol}")
            lines.append(f"  Harga acuan : {_rp(sig.entry_reference)}")
            if sig.explanation_context:
                for w in sig.explanation_context[:5]:
                    lines.append(f"  • {w}")
        else:
            lines.append("⚠️ Tidak ada saham yang memenuhi seluruh syarat pembelian saat ini.")
            reasons = list(report.no_signal_reasons or [])
            if reasons:
                lines.append("")
                lines.append("Alasan dari sistem:")
                for r in reasons[:6]:
                    lines.append(f"  • {r}")

        filled_syms = list(getattr(report, "filled_symbols", None) or [])
        n_fill = int(getattr(report, "signals_filled", 0) or 0)
        if n_fill > 1 and filled_syms:
            lines.append("")
            lines.append(f"Paper fill cycle ini ({n_fill}):")
            for sym in filled_syms[:10]:
                mark = " ← sinyal utama" if sig and sym == sig.symbol else ""
                lines.append(f"  • {sym} — PAPER_FILLED{mark}")

        lines += ["", _SEP]
        return lines

    def _system_block(self, report: CycleReport) -> list[str]:
        sig = report.signal
        n_pos = len(report.portfolio.open_positions) if report.portfolio and report.portfolio.open_positions else 0
        filled = int(getattr(report, "signals_filled", 0) or 0)
        received = int(getattr(report, "signals_received", 0) or 0)
        if received <= 0 and sig and sig.decision in ("BUY", "SELL"):
            received = 1
        if filled <= 0 and sig and (getattr(sig, "fill_status", "") or "") in (
            "PAPER_FILLED", "FULL_FILL", "FILLED", "FULL FILL"
        ):
            filled = 1
        filled_syms = list(getattr(report, "filled_symbols", None) or [])
        if not filled_syms and sig and sig.decision == "BUY" and filled:
            filled_syms = [sig.symbol]

        gate = report.risk_gate or "-"
        lines = [
            "🔎 STATUS SISTEM",
            "",
            f"Sinyal dievaluasi      : {received}",
            f"Paper fill hari ini    : {filled}",
            f"Posisi terbuka         : {n_pos}",
        ]
        if filled_syms:
            lines.append(f"Aset terisi (cycle)    : {', '.join(filled_syms)}")
        lines += [
            f"Risk gate              : {gate}",
            f"Status sistem          : {_system_status(report)}",
            f"Data quality           : {report.dq_status or '-'}",
            f"Governor               : {report.governor_action or '-'}",
            "",
            _SEP,
            f"⚙️ Engine: {report.model_version or (sig.model_version if sig else None) or '-'}",
        ]
        if sig and sig.signal_id:
            lines.append(f"SignalID (utama): {sig.signal_id}")
        if report.data_source:
            lines.append(f"Sumber data: {report.data_source}")
        return lines

    def _footer(self, report: CycleReport) -> list[str]:
        lines = ["", "──────────────────────────────", "⚠️ MODE OPERASI"]
        if report.live_execution:
            lines.append("Mode LIVE sesuai konfigurasi sistem.")
        else:
            lines.append("PAPER TRADING — INSTANT SIMULATION")
            lines.append("Tidak ada order yang dikirim ke broker.")
            lines.append("Tidak ada live execution.")
            lines.append("Fill hanya dicatat di paper portfolio ledger.")
            try:
                from src.python.ops.paper_portfolio import simulation_assumptions
                sa = simulation_assumptions()
                buy = sa.get("buy_fee_bps", 15)
                exit_f = sa.get("exit_fee_bps", 25)
                slip = sa.get("slippage_bps", 5)
                rt = float(buy) + float(exit_f) + 2.0 * float(slip)
                lines.append(f"Fee model   : {sa.get('fee_model', 'SIMULATION')} (bukan tarif broker)")
                lines.append(f"Buy fee     : {buy} bps • Exit fee: {exit_f} bps")
                lines.append(f"Slippage    : {slip} bps per side • RT est: {rt:.0f} bps")
                lines.append(f"Intrabar    : {sa.get('intrabar_policy', 'SL_PRECEDENCE')}")
            except Exception:
                lines.append("Fee model   : SIMULATION (bukan tarif broker)")
                lines.append("Buy fee     : 15 bps • Exit fee: 25 bps")
                lines.append("Slippage    : 5 bps/side • RT est: 50 bps")
            lines.append("Output ini adalah hasil sistem dan bukan")
            lines.append("rekomendasi investasi personal.")
            lines.append("NO LIVE EXECUTION")
        return lines


def compose_telegram_message(report: CycleReport) -> str:
    return DeterministicComposer().compose(report)
