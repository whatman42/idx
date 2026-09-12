"""IDX operational signal bot — SIGNAL ONLY + continuous paper portfolio (Rp10M).
Default scan: FULL IDX universe (symbols=ALL).
"""
from __future__ import annotations
import hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo
import pandas as pd
import typer
from src.python.data.costs import CostModel
from src.python.data.quality import validate_ohlcv
from src.python.market.providers import SyntheticProvider
from src.python.market.calendar import is_trading_day
from src.python.market.universe import resolve_symbols, universe_meta
from src.python.notify.telegram import TelegramProvider
from src.python.ops.notify_state import NotifyStateStore
from src.python.ops.telegram_format import format_halt_message, format_signal_message, notification_id
from src.python.ops.freshness import freshness_gate
from src.python.ops.paper_portfolio import (
    DEFAULT_INITIAL_CAPITAL, PaperPortfolioStore, apply_long_entry,
    mark_to_market, new_session, summary as portfolio_summary, paper_reset_scope,
)
from src.python.validation.economic_sim import simulate_long_only
from src.python.ops.readiness import assess_readiness

app = typer.Typer(add_completion=False)
JKT = ZoneInfo("Asia/Jakarta")
VALID_MODES = {"TEST", "PAPER", "OPERATIONAL"}

def _now_jkt() -> datetime:
    return datetime.now(JKT)

def _trading_date_jkt() -> str:
    return _now_jkt().strftime("%Y-%m-%d")

def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""

def _is_market_hours_ok(*, force: bool = False) -> tuple[bool, str]:
    if force: return True, "forced"
    now = _now_jkt()
    if now.weekday() >= 5: return False, "weekend_asia_jakarta"
    if now.hour * 60 + now.minute < 15 * 60 + 30:
        return False, f"before_eod_window_jkt_{now.strftime('%H:%M')}"
    return True, "ok"

def _load_bars(mode: str, csv_path: Optional[str], symbols: list[str]):
    if mode == "TEST" and not csv_path:
        # TEST uses small synthetic subset even if ALL requested (speed)
        test_syms = symbols[:5] if symbols else ["BBCA", "BBRI", "TLKM"]
        c = SyntheticProvider(n=80, seed=42).fetch(test_syms)
        return c.df, c.source, hashlib.sha256(c.df.to_csv(index=False).encode()).hexdigest()
    if csv_path and Path(csv_path).exists():
        p = Path(csv_path); df = pd.read_csv(p)
        if "timestamp" in df.columns: df["timestamp"] = pd.to_datetime(df["timestamp"])
        if symbols and "symbol" in df.columns: df = df[df["symbol"].isin(symbols)]
        return df, f"csv:{p.name}", _sha_file(p)
    env_csv = os.getenv("IDX_CSV_PATH", "")
    if env_csv and Path(env_csv).exists():
        p = Path(env_csv); df = pd.read_csv(p)
        if "timestamp" in df.columns: df["timestamp"] = pd.to_datetime(df["timestamp"])
        if symbols and "symbol" in df.columns: df = df[df["symbol"].isin(symbols)]
        return df, f"csv:{p.name}", _sha_file(p)
    if mode in ("PAPER", "OPERATIONAL") or os.getenv("IDX_ALLOW_YFINANCE", "") == "1":
        try:
            from src.python.market.yfinance_provider import YFinanceProvider
            c = YFinanceProvider(period=os.getenv("IDX_YF_PERIOD", "3mo"), batch_size=int(os.getenv("IDX_YF_BATCH", "80"))).fetch(symbols)
            h = hashlib.sha256(c.df.to_csv(index=False).encode()).hexdigest()
            return c.df, c.source, h
        except Exception as e:
            if mode == "OPERATIONAL":
                raise RuntimeError(f"OPERATIONAL data fetch failed: {e}") from e
    if mode == "OPERATIONAL":
        raise RuntimeError("OPERATIONAL requires IDX_CSV_PATH, --csv, or yfinance public fetch")
    c = SyntheticProvider(n=80, seed=42).fetch((symbols or ["BBCA"])[:5])
    return c.df, c.source, hashlib.sha256(c.df.to_csv(index=False).encode()).hexdigest()

def _naive_signals_from_bars(bars: pd.DataFrame, *, lookback: int = 20) -> pd.DataFrame:
    rows = []
    for sym, g in bars.groupby("symbol"):
        g = g.sort_values("timestamp").reset_index(drop=True)
        if len(g) < lookback + 2: continue
        close = g["close"].astype(float); sma = close.rolling(lookback).mean()
        for i in range(lookback, len(g)):
            side = 1 if close.iloc[i] > sma.iloc[i] else 0
            conf = abs(float(close.iloc[i] / sma.iloc[i] - 1.0)) if sma.iloc[i] else 0.0
            rows.append({"timestamp": g.iloc[i]["timestamp"], "symbol": str(sym), "side": side,
                         "confidence": min(0.99, 0.5 + conf * 5)})
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence"])

def _latest_day_signals(signals: pd.DataFrame) -> pd.DataFrame:
    if signals.empty: return signals
    ts = pd.to_datetime(signals["timestamp"]); last = ts.max().normalize()
    return signals[ts.dt.normalize() == last].copy()

def _telegram_enabled(mode: str) -> tuple[bool, str]:
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat: return False, "TELEGRAM_DISABLED"
    if mode == "TEST" and os.getenv("IDX_TELEGRAM_ALLOW_TEST", "") != "1":
        return False, "TEST_MODE_TELEGRAM_SUPPRESSED"
    if mode == "PAPER" and os.getenv("IDX_TELEGRAM_ALLOW_PAPER", "") != "1":
        return False, "PAPER_MODE_TELEGRAM_SUPPRESSED"
    return True, "OK"

def _write_report(art_path: Path, report: dict) -> None:
    art_path.mkdir(parents=True, exist_ok=True)
    (art_path / "operational_report.json").write_text(json.dumps(report, indent=2, default=str))

def _send_plain(provider: TelegramProvider, text: str) -> None:
    import httpx
    url = f"https://api.telegram.org/bot{provider.bot_token}/sendMessage"
    httpx.post(url, json={"chat_id": provider.chat_id, "text": text}, timeout=provider.timeout).raise_for_status()

def _notify_halt(mode, reason, trading_date, details, state_path, report):
    allow, why = _telegram_enabled(mode)
    report["telegram_enable_reason"] = why
    if not allow:
        report["telegram_status"] = "DISABLED"; return
    provider = TelegramProvider.from_env()
    if provider is None:
        report["telegram_status"] = "TELEGRAM_DISABLED"; return
    try:
        _send_plain(provider, format_halt_message(reason=reason, trading_date=trading_date, details=details))
        report["telegram_status"] = "HALT_SENT"
    except Exception:
        report["telegram_status"] = "HALT_FAILED"

@app.command()
def run(
    mode: str = typer.Option("TEST"),
    csv: Optional[str] = typer.Option(None),
    symbols: str = typer.Option("ALL", help="ALL = full IDX universe, or comma list"),
    state_dir: str = typer.Option("state/ops"),
    artifact_dir: str = typer.Option("artifacts/ops"),
    force_schedule: bool = typer.Option(False),
    hold_bars: int = typer.Option(5),
    fee_bps: float = typer.Option(15.0),
    slippage_bps: float = typer.Option(5.0),
    model_version: str = typer.Option("ops_sma_v0"),
    reset_portfolio: bool = typer.Option(False),
    initial_capital: float = typer.Option(DEFAULT_INITIAL_CAPITAL),
):
    mode = mode.upper().strip()
    if mode not in VALID_MODES: raise typer.BadParameter(str(VALID_MODES))
    run_id = f"ops_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    trading_date = _trading_date_jkt()
    syms = resolve_symbols(symbols)
    u_meta = universe_meta()
    state_path = Path(state_dir); state_path.mkdir(parents=True, exist_ok=True)
    art_path = Path(artifact_dir); art_path.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "run_id": run_id, "trading_date": trading_date, "mode": mode,
        "workflow_run_id": os.getenv("GITHUB_RUN_ID", ""),
        "git_commit": os.getenv("GITHUB_SHA", "")[:40], "timezone": "Asia/Jakarta",
        "signal_only": True, "live_execution": False,
        "economic_edge": "UNVERIFIED", "production_ready": False, "strategy_changed": False,
        "universe_source": u_meta.get("source"), "universe_count": u_meta.get("count"),
        "symbols_requested_count": len(syms),
        "scan_mode": "FULL_UNIVERSE" if len(syms) > 50 else "SUBSET",
    }
    ok_sched, sched_reason = _is_market_hours_ok(force=force_schedule or mode == "TEST")
    report["schedule"] = {"ok": ok_sched, "reason": sched_reason}
    if not ok_sched and mode == "OPERATIONAL":
        report["status"] = "BLOCKED_SCHEDULE"; _write_report(art_path, report); raise SystemExit(0)
    try:
        bars, source, data_hash = _load_bars(mode, csv, syms)
    except Exception as e:
        report.update({"status": "DATA_FAILURE", "error": str(e), "signals_generated": 0})
        _notify_halt(mode, "DATA FAILURE", trading_date, str(e), state_path, report)
        _write_report(art_path, report); raise SystemExit(1)
    report["data_source"] = source; report["data_hash"] = data_hash
    report["symbols"] = sorted(bars["symbol"].astype(str).unique().tolist()) if "symbol" in bars.columns else syms
    report["symbols_loaded_count"] = len(report["symbols"])
    report["rows"] = len(bars)
    q = validate_ohlcv(bars)
    report["dq_status"] = "PASS" if q.ok else "FAIL"
    if not q.ok:
        report["status"] = "HALTED_DATA_QUALITY"; report["signals_generated"] = 0
        _notify_halt(mode, "DATA QUALITY FAILURE", trading_date, "; ".join(q.issues[:5]), state_path, report)
        _write_report(art_path, report); raise SystemExit(1)
    fg = freshness_gate(bars, require_current_day=(mode == "OPERATIONAL"), max_stale_days=2.0 if mode != "TEST" else 30.0)
    report["freshness"] = fg
    if mode != "TEST" and fg.get("status") != "PASS":
        report["status"] = "HALTED_STALE_DATA"; report["signals_generated"] = 0
        _notify_halt(mode, "DATA STALE", trading_date, fg.get("reason", ""), state_path, report)
        _write_report(art_path, report); raise SystemExit(1)

    pf_store = PaperPortfolioStore(state_path / "paper_portfolio.json", archive_dir=state_path / "sessions")
    report["reset_portfolio"] = bool(reset_portfolio)
    if reset_portfolio:
        old_pf, pf = pf_store.archive_and_reset(initial_capital=initial_capital, model_version=model_version)
        report.update({"portfolio_reset": True, "reset_scope": paper_reset_scope(),
            "archived_session_id": getattr(old_pf, "simulation_session_id", None),
            "simulation_session_id": pf.simulation_session_id, "status": "PORTFOLIO_RESET",
            "paper_portfolio": portfolio_summary(pf), "intelligence_state": "PRESERVED",
            "production_pointer_changed": False, "retrain_triggered": False})
        _write_report(art_path, report); print(json.dumps(report, indent=2, default=str)); raise SystemExit(0)
    try:
        pf = pf_store.load() if pf_store.exists() else new_session(initial_capital=initial_capital, model_version=model_version)
        if not pf_store.exists(): pf_store.save_atomic(pf)
    except Exception as e:
        report.update({"status": "HALTED_CORRUPT_PORTFOLIO", "error": str(e), "signals_generated": 0})
        _notify_halt(mode, "CORRUPTED PORTFOLIO STATE", trading_date, str(e), state_path, report)
        _write_report(art_path, report); raise SystemExit(1)
    report["simulation_session_id"] = pf.simulation_session_id

    all_sig = _naive_signals_from_bars(bars)
    day_sig = _latest_day_signals(all_sig)
    long_sig = day_sig[day_sig["side"] == 1] if not day_sig.empty else day_sig
    report["signals_generated"] = int(len(long_sig))
    report["model"] = model_version
    report["governor_action"] = "ALLOW_PAPER_SIGNAL"
    report["timing"] = "signal_T_execute_open_Tplus1"
    paper_signals = all_sig.copy()
    if not paper_signals.empty: paper_signals["side"] = paper_signals["side"].astype(int)
    sim = simulate_long_only(bars, paper_signals if not paper_signals.empty else pd.DataFrame(columns=["timestamp","symbol","side"]),
        cost=CostModel(fee_bps, slippage_bps), hold_bars=hold_bars)
    report["paper_fills"] = (sim.get("metrics") or {}).get("total_trades", 0)
    report["safety_status"] = "PASS"
    signal_payloads = [{"symbol": str(r["symbol"]), "side_label": "BUY", "signal": "BUY",
        "confidence": float(r.get("confidence", 0.5)), "risk": "PASS", "rrr": None} for _, r in long_sig.iterrows()]
    signal_payloads = sorted(signal_payloads, key=lambda x: float(x.get("confidence") or 0), reverse=True)
    report["signals_scanned"] = int(len(signal_payloads))
    max_notify = int(os.getenv("IDX_MAX_NOTIFY_SIGNALS", "20"))
    max_portfolio = int(os.getenv("IDX_MAX_PORTFOLIO_ENTRIES", "15"))
    notify_payloads = signal_payloads[:max_notify]
    portfolio_candidates = signal_payloads[:max_portfolio]

    marks = {}
    last_ts = {}
    if not bars.empty:
        for _, row in bars.sort_values("timestamp").groupby("symbol").tail(1).iterrows():
            marks[str(row["symbol"])] = float(row["close"])
            last_ts[str(row["symbol"])] = str(row["timestamp"])
    fills_cls = []
    for s in portfolio_candidates:
        sym = str(s["symbol"])
        ts = last_ts.get(sym, trading_date)
        sid = f"sig_{trading_date}_{sym}_{model_version}"
        px = float(marks.get(sym, 0.0))
        if px <= 0: fills_cls.append("SKIPPED_INVALID_DATA"); continue
        pf, trade, cls = apply_long_entry(pf, symbol=sym, price=px, weight=0.05, signal_id=sid, timestamp=ts,
            fee_bps=fee_bps, slippage_bps=slippage_bps)
        fills_cls.append(cls)
    pf = mark_to_market(pf, marks, trading_date)
    pf.last_processed_trading_day = trading_date
    pf.model_version = model_version
    try:
        pf_store.save_atomic(pf); report["persistence_status"] = "PASS"
    except Exception as e:
        report.update({"persistence_status": "FAIL", "status": "HALTED_PERSISTENCE", "error": str(e)})
        _write_report(art_path, report); raise SystemExit(1)
    report["paper_portfolio"] = portfolio_summary(pf, marks)
    report["paper_fill_classifications"] = fills_cls
    rr = assess_readiness(
        signal_bot_ok=True,
        paper_portfolio_ok=report.get("persistence_status") == "PASS",
        data_source=str(report.get("data_source", "")),
        dq_pass=report.get("dq_status") == "PASS",
        freshness_status=str((report.get("freshness") or {}).get("status", "")),
        cost_status="UNVERIFIED_ASSUMPTION",
        edge_status="UNVERIFIED",
        multi_day_paper_ok=False,
    )
    report["readiness"] = rr.to_dict()
    report["production_ready"] = bool(rr.production_ready)
    report["production_ready_100pct"] = bool(rr.production_ready_100pct)
    report["economic_edge"] = rr.economic_edge

    nstore = NotifyStateStore(state_path / "notify_state.json")
    if nstore.is_corrupt:
        report["status"] = "HALTED_CORRUPT_STATE"
        _notify_halt(mode, "STATE CORRUPTION", trading_date, "notify_state corrupt", state_path, report)
        _write_report(art_path, report); raise SystemExit(1)
    notified = already = 0
    allow_tg, tg_reason = _telegram_enabled(mode)
    report["telegram_enable_reason"] = tg_reason
    if not notify_payloads:
        report["production_ready"] = False
        report["production_ready_100pct"] = False
        report.update({"status": "NO_SIGNAL", "signals_notified": 0, "telegram_status": "NO_SIGNAL"})
        _write_report(art_path, report); print(json.dumps(report, indent=2, default=str)); raise SystemExit(0)
    to_send = []
    for s in notify_payloads:
        nid = notification_id(trading_date=trading_date, symbol=s["symbol"], signal_type="BUY", model_version=model_version)
        s["notification_id"] = nid
        if nstore.was_notified(nid):
            nstore.mark(nid, "ALREADY_NOTIFIED", {"trading_date": trading_date}); already += 1
        else:
            to_send.append(s); nstore.mark(nid, "GENERATED", {"trading_date": trading_date})
    provider = TelegramProvider.from_env() if allow_tg else None
    tg_status = "TELEGRAM_DISABLED" if provider is None else ("ALREADY_NOTIFIED" if not to_send else "DISABLED")
    if provider and to_send:
        text = format_signal_message(trading_date=trading_date, signals=to_send,
            portfolio={"cash": report["paper_portfolio"].get("cash"), "equity": report["paper_portfolio"].get("equity"),
                "exposure": report["paper_portfolio"].get("exposure"),
                "positions": len(report["paper_portfolio"].get("open_positions") or {}),
                "initial_capital": report["paper_portfolio"].get("initial_capital")},
            governor=report["governor_action"], dq=report["dq_status"], mode=mode)
        try:
            _send_plain(provider, text)
            for s in to_send:
                nstore.mark(s["notification_id"], "NOTIFIED", {"trading_date": trading_date}); notified += 1
            tg_status = "SENT"
        except Exception as e:
            tg_status = "FAILED"; report["telegram_error"] = type(e).__name__
            report["status"] = "SIGNAL_OK_TELEGRAM_FAILED"
    report["signals_notified"] = notified
    report["signals_already_notified"] = already
    report["telegram_status"] = tg_status
    if "status" not in report: report["status"] = "SUCCESS"
    (state_path / "last_run.json").write_text(json.dumps({"run_id": run_id, "trading_date": trading_date, "mode": mode}, indent=2))
    _write_report(art_path, report)
    print(json.dumps(report, indent=2, default=str))

if __name__ == "__main__":
    app()
