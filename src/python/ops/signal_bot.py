"""IDX operational signal bot — SIGNAL ONLY + continuous paper portfolio (Rp10M).
Default scan: FULL IDX universe (symbols=ALL).
Telegram: deterministic dashboard + optional Gemini executive summary (interpretation only).
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
from src.python.ops.telegram_format import notification_id
from src.python.ops.freshness import freshness_gate
from src.python.ops.paper_portfolio import (
    DEFAULT_INITIAL_CAPITAL, DEFAULT_LOT_SIZE, PaperPortfolioStore, apply_long_entry,
    mark_to_market, new_session, summary as portfolio_summary, paper_reset_scope,
    process_tp_sl_exits, compute_tp_sl,
)
from src.python.ops.risk_gate import gate_new_entry, risk_defaults, estimate_open_heat
from src.python.validation.economic_sim import simulate_long_only
from src.python.ops.readiness import assess_readiness
from src.python.llm.gemini_narrator import narrate_halt
from src.python.llm.executive_summary_gemini import generate_executive_summary
from src.python.reporting.builder import build_buy_signal, build_cycle_report
from src.python.reporting.finance import shares_from_lots, lots_from_shares, SHARES_PER_LOT
from src.python.reporting.llm_boundary import compose_with_executive_summary
from src.python.reporting.executive_summary import (
    build_executive_payload, payload_fingerprint, should_emit_summary, mark_emitted,
)
from src.python.reporting.composer import compose_telegram_message
from src.python.reporting.validation import validate_cycle_report

def _telegram_text_from_cycle(cycle, report: dict) -> tuple:
    """Deterministic dashboard + optional Gemini executive summary (reporting only)."""
    payload = build_executive_payload(cycle)
    fp = payload_fingerprint(payload)
    exec_text, obs = generate_executive_summary(payload, use_llm=True)
    obs_d = obs.to_dict()
    obs_d["input_fingerprint"] = fp
    if not should_emit_summary(fp, channel="telegram_exec"):
        text = compose_telegram_message(cycle)
        obs_d["duplicate_suppressed"] = True
        return text, "deterministic", obs_d
    text, src = compose_with_executive_summary(cycle, executive_text=exec_text, executive_enabled=True)
    mark_emitted(fp, channel="telegram_exec")
    return text, src, obs_d

app = typer.Typer(add_completion=False)
JKT = ZoneInfo("Asia/Jakarta")
VALID_MODES = {"TEST", "PAPER", "OPERATIONAL"}
TOP_N_SIGNAL = 3  # rank top-N; risk_gate decides how many actually fill
ENTRY_WEIGHT = 0.05  # fallback only if risk_gate unavailable

def _estimate_atr(g: pd.DataFrame, window: int = 14):  # ATR_WINDOW
    """True-range ATR from OHLCV group; None if insufficient data."""
    need = ["high", "low", "close"]
    if any(c not in g.columns for c in need) or len(g) < window + 1:
        return None
    h = g["high"].astype(float)
    l = g["low"].astype(float)
    c = g["close"].astype(float)
    prev_c = c.shift(1)
    tr = pd.concat([(h - l).abs(), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window).mean().iloc[-1]
    try:
        atr_f = float(atr)
    except (TypeError, ValueError):
        return None
    if atr_f != atr_f or atr_f <= 0:
        return None
    return atr_f


def _atr_map(bars: pd.DataFrame, window: int = 14) -> dict:
    out = {}
    if bars is None or getattr(bars, "empty", True) or "symbol" not in bars.columns:
        return out
    for sym, g in bars.groupby("symbol"):
        g = g.sort_values("timestamp") if "timestamp" in g.columns else g
        atr = _estimate_atr(g, window=window)
        if atr is not None:
            out[str(sym)] = atr
    return out


def _exit_levels(entry_px: float, atr, hold_bars: int = 8):
    """TP/SL via optimized ExitPlan (ATR 1.8/3.2 + trail from ATR); static fallback."""
    try:
        from src.python.strategy.exits import (
            ATR_WINDOW,
            DEFAULT_TIME_STOP_BARS,
            atr_exit_defaults,
            build_exit_plan,
        )
        ts = int(hold_bars) if hold_bars and hold_bars > 0 else DEFAULT_TIME_STOP_BARS
        plan = build_exit_plan(
            entry_price=entry_px,
            atr=atr,
            time_stop_bars=ts,
            # trailing_pct=None → auto from ATR when atr present
        )
        tp = round(entry_px * (1.0 + plan.tp_pct), 2)
        sl = round(entry_px * (1.0 - plan.sl_pct), 2)
        meta = {
            "sl_pct": float(plan.sl_pct),
            "tp_pct": float(plan.tp_pct),
            "method": plan.method,
            "time_stop_bars": int(plan.time_stop_bars),
            "trailing_pct": float(plan.trailing_pct or 0.0),
            "rrr": round(plan.tp_pct / plan.sl_pct, 2) if plan.sl_pct > 0 else 2.0,
            "atr_window": ATR_WINDOW,
            "tunables": atr_exit_defaults(),
        }
        return tp, sl, meta
    except Exception:
        tp = round(entry_px * 1.06, 2)
        sl = round(entry_px * 0.97, 2)
        return tp, sl, {
            "sl_pct": 0.03, "tp_pct": 0.06, "method": "static_pct",
            "time_stop_bars": int(hold_bars or 8), "trailing_pct": 0.0, "rrr": 2.0,
        }


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
                         "confidence": min(0.99, 0.5 + conf * 5), "close": float(close.iloc[i])})
    return pd.DataFrame(rows) if rows else pd.DataFrame(columns=["timestamp", "symbol", "side", "confidence", "close"])

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
    narration = narrate_halt(
        trading_date=trading_date, mode=mode, reason=reason, details=details, report=report,
    )
    report["telegram_narration"] = {
        "kind": "halt", "narrator": narration.get("narrator"), "fallback": narration.get("fallback"),
        "model": narration.get("model"), "reason": narration.get("reason"),
    }
    if not allow:
        report["telegram_status"] = "DISABLED"; return
    provider = TelegramProvider.from_env()
    if provider is None:
        report["telegram_status"] = "TELEGRAM_DISABLED"; return
    try:
        _send_plain(provider, narration["text"])
        report["telegram_status"] = "HALT_SENT"
    except Exception as e:
        report["telegram_status"] = "HALT_FAILED"
        report["telegram_error"] = type(e).__name__

@app.command()
def run(
    mode: str = typer.Option("TEST"),
    csv: Optional[str] = typer.Option(None),
    symbols: str = typer.Option("ALL", help="ALL = full IDX universe, or comma list"),
    state_dir: str = typer.Option("state/ops"),
    artifact_dir: str = typer.Option("artifacts/ops"),
    force_schedule: bool = typer.Option(False),
    hold_bars: int = typer.Option(8, help="time-stop calendar days when position open"),
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
        "top_n_signal": TOP_N_SIGNAL,
        "risk_geometry": {"sl_pct": 0.03, "tp_pct": 0.06, "rrr": "1:2", "engine": "adaptive_atr_opt_v1"},
    }
    ok_sched, sched_reason = _is_market_hours_ok(force=force_schedule or mode == "TEST")
    report["schedule"] = {"ok": ok_sched, "reason": sched_reason}
    if not ok_sched and mode == "OPERATIONAL":
        report["status"] = "BLOCKED_SCHEDULE"; _write_report(art_path, report); print(json.dumps(report, indent=2, default=str)); raise SystemExit(0)
    try:
        bars, source, data_hash = _load_bars(mode, csv, syms)
    except Exception as e:
        report.update({"status": "DATA_FAILURE", "error": str(e), "signals_generated": 0})
        _notify_halt(mode, "DATA FAILURE", trading_date, str(e), state_path, report)
        _write_report(art_path, report); print(json.dumps(report, indent=2, default=str)); raise SystemExit(1)
    report["data_source"] = source; report["data_hash"] = data_hash
    report["symbols"] = sorted(bars["symbol"].astype(str).unique().tolist()) if "symbol" in bars.columns else syms
    report["symbols_loaded_count"] = len(report["symbols"])
    report["rows"] = len(bars)
    q = validate_ohlcv(bars)
    report["dq_status"] = "PASS" if q.ok else "FAIL"
    if not q.ok:
        report["status"] = "HALTED_DATA_QUALITY"; report["signals_generated"] = 0
        _notify_halt(mode, "DATA QUALITY FAILURE", trading_date, "; ".join(q.issues[:5]), state_path, report)
        _write_report(art_path, report); print(json.dumps(report, indent=2, default=str)); raise SystemExit(1)
    fg = freshness_gate(
        bars,
        require_current_day=(mode == "OPERATIONAL"),
        max_stale_days=2.0 if mode != "TEST" else 30.0,
        allow_last_session_on_holiday=True,
    )
    report["freshness"] = fg
    if mode != "TEST" and fg.get("status") != "PASS":
        reason = str(fg.get("reason", ""))
        report["signals_generated"] = 0
        if reason in ("NON_TRADING_DAY",) or (reason.startswith("STALE") and mode == "PAPER"):
            report["status"] = "BLOCKED_FRESHNESS"
            _write_report(art_path, report)
            print(json.dumps(report, indent=2, default=str))
            raise SystemExit(0)
        report["status"] = "HALTED_STALE_DATA"
        _notify_halt(mode, "DATA STALE", trading_date, reason, state_path, report)
        _write_report(art_path, report)
        print(json.dumps(report, indent=2, default=str))
        raise SystemExit(1)

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
        _write_report(art_path, report); print(json.dumps(report, indent=2, default=str)); raise SystemExit(1)
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
    marks = {}
    last_ts = {}
    if not bars.empty:
        for _, row in bars.sort_values("timestamp").groupby("symbol").tail(1).iterrows():
            marks[str(row["symbol"])] = float(row["close"])
            last_ts[str(row["symbol"])] = str(row["timestamp"])

    pf = mark_to_market(pf, marks, trading_date)
    pf, exits = process_tp_sl_exits(pf, marks, trading_date, fee_bps=25.0, slippage_bps=slippage_bps)
    report["exits_today"] = exits
    report["exits_count"] = len(exits)

    atr_by_sym = _atr_map(bars)
    report["exit_engine"] = {
        "mode": "adaptive_atr_opt_v1",
        "fallback": "static_3_6",
        "symbols_with_atr": len(atr_by_sym),
        "time_stop_bars_default": int(hold_bars),
        "trailing_pct_when_atr": "1.5xATR_clamped_2_to_6pct",
    }
    signal_payloads = []
    for _, r in long_sig.iterrows():
        sym = str(r["symbol"])
        px = float(r.get("close") or marks.get(sym, 0.0))
        if px <= 0:
            continue
        conf = float(r.get("confidence", 0.5))
        # Entry noise filter: require meaningful distance above SMA (confidence proxy)
        if conf < 0.005:
            continue
        tp, sl, emeta = _exit_levels(px, atr_by_sym.get(sym), hold_bars=hold_bars)
        signal_payloads.append({
            "symbol": sym, "side_label": "BUY", "signal": "BUY", "confidence": conf,
            "price": px, "entry_price": px, "tp": tp, "sl": sl, "risk": "PASS",
            "rrr": emeta.get("rrr", 2.0),
            "exit_method": emeta.get("method", "static_pct"),
            "time_stop_bars": emeta.get("time_stop_bars", hold_bars),
            "trailing_pct": emeta.get("trailing_pct", 0.0),
            "sl_pct": emeta.get("sl_pct"), "tp_pct": emeta.get("tp_pct"),
            "why": f"Ranking confidence ({conf*100:.0f}%) vs SMA20; exit={emeta.get('method')}",
        })
    signal_payloads = sorted(signal_payloads, key=lambda x: float(x.get("confidence") or 0), reverse=True)
    report["signals_scanned"] = int(len(signal_payloads))
    top1 = signal_payloads[:TOP_N_SIGNAL]
    notify_payloads = list(top1)
    portfolio_candidates = list(top1)

    fills_cls = []
    filled_trades = []
    open_syms = set(pf.open_positions().keys())
    new_entries_today = 0
    eq0 = float(pf.equity(marks))
    dd0 = float(pf.drawdown(marks))
    exp0 = float(pf.exposure(marks))
    report["risk_gate"] = risk_defaults()
    report["portfolio_heat_pre"] = estimate_open_heat(pf.positions, equity=eq0)
    for s in portfolio_candidates:
        sym = str(s["symbol"])
        ts = last_ts.get(sym, trading_date)
        sid = f"sig_{trading_date}_{sym}_{model_version}"
        px = float(s.get("price") or marks.get(sym, 0.0))
        if px <= 0:
            fills_cls.append("SKIPPED_INVALID_DATA")
            continue
        # Ops policy: no second long while position still open (anti double-entry / fee bleed)
        if sym in open_syms:
            fills_cls.append("SKIPPED_EXISTING_POSITION")
            s.update({
                "fill_status": "SKIPPED_EXISTING_POSITION",
                "why": s.get("why", "") + " | fill=SKIPPED_EXISTING_POSITION (already holding)",
            })
            continue
        # Institutional risk gate: 1% risk / ATR stop → weight; heat/DD/max-pos fail-closed
        stop_pct = float(s.get("sl_pct") or 0.0)
        if stop_pct <= 0 and px > 0 and float(s.get("sl") or 0) > 0:
            stop_pct = max(0.0, (px - float(s["sl"])) / px)
        if stop_pct <= 0:
            stop_pct = 0.03
        gate = gate_new_entry(
            equity=float(pf.equity(marks)),
            cash=float(pf.cash),
            open_positions=pf.positions,
            current_drawdown=float(pf.drawdown(marks)),
            stop_distance_pct=stop_pct,
            portfolio_exposure=float(pf.exposure(marks)),
            new_entries_today=new_entries_today,
        )
        s["risk_gate"] = gate.to_dict()
        if not gate.allow_entry:
            fills_cls.append(f"SKIPPED_RISK_{gate.reason}")
            s.update({
                "fill_status": f"SKIPPED_RISK_{gate.reason}",
                "why": s.get("why", "") + f" | risk_gate={gate.reason}",
            })
            continue
        entry_weight = float(gate.weight) if gate.weight > 0 else ENTRY_WEIGHT
        pf, trade, cls = apply_long_entry(
            pf, symbol=sym, price=px, weight=entry_weight, signal_id=sid, timestamp=ts,
            fee_bps=fee_bps, slippage_bps=slippage_bps, tp=float(s["tp"]), sl=float(s["sl"]),
            allow_scale_in=False,
            time_stop_bars=int(s.get("time_stop_bars") or hold_bars or 0),
            trailing_pct=float(s.get("trailing_pct") or 0.0),
            exit_method=str(s.get("exit_method") or "static_pct"),
        )
        if cls == "FULL_FILL":
            open_syms.add(sym)
            new_entries_today += 1
        fills_cls.append(cls)
        if trade:
            filled_trades.append(trade)
            s.update({
                "lots": trade.get("lots"), "qty": trade.get("qty"),
                "notional": trade.get("notional"), "total_cost": trade.get("total_cost"),
                "entry_price": trade.get("price"), "price": trade.get("price"),
                "tp": trade.get("tp"), "sl": trade.get("sl"), "fill_status": cls,
            })
        else:
            eq = pf.equity(marks)
            target = eq * ENTRY_WEIGHT
            exec_px = px * (1.0 + slippage_bps / 10000.0)
            qty = (target / exec_px) // DEFAULT_LOT_SIZE * DEFAULT_LOT_SIZE if exec_px > 0 else 0
            s.update({
                "lots": qty / DEFAULT_LOT_SIZE if qty else 0, "qty": qty,
                "notional": qty * exec_px, "total_cost": qty * exec_px * (1 + fee_bps / 10000.0),
                "fill_status": cls, "why": s.get("why", "") + f" | fill={cls}",
            })
    pf = mark_to_market(pf, marks, trading_date)
    pf.last_processed_trading_day = trading_date
    pf.model_version = model_version
    try:
        pf_store.save_atomic(pf); report["persistence_status"] = "PASS"
    except Exception as e:
        report.update({"persistence_status": "FAIL", "status": "HALTED_PERSISTENCE", "error": str(e)})
        _write_report(art_path, report); print(json.dumps(report, indent=2, default=str)); raise SystemExit(1)
    report["paper_portfolio"] = portfolio_summary(pf, marks)
    report["paper_fill_classifications"] = fills_cls
    report["filled_trades"] = filled_trades
    # Explicit skip counters for daily audit trail
    report["skipped_existing_position"] = sum(1 for c in fills_cls if c == "SKIPPED_EXISTING_POSITION")
    report["skipped_cooldown"] = sum(1 for c in fills_cls if c == "SKIPPED_COOLDOWN")
    report["skipped_cash"] = sum(1 for c in fills_cls if c == "SKIPPED_CASH")
    report["fills_full"] = sum(1 for c in fills_cls if c == "FULL_FILL")
    report["portfolio_heat_post"] = estimate_open_heat(pf.positions, equity=float(pf.equity(marks)))
    report["risk_skips"] = sum(1 for c in fills_cls if str(c).startswith("SKIPPED_RISK_"))
    report["fills_already_applied"] = sum(1 for c in fills_cls if c == "ALREADY_APPLIED")
    report["top_signal"] = top1[0] if top1 else None
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
        _write_report(art_path, report); print(json.dumps(report, indent=2, default=str)); raise SystemExit(1)
    notified = already = 0
    allow_tg, tg_reason = _telegram_enabled(mode)
    report["telegram_enable_reason"] = tg_reason
    if not notify_payloads:
        report["production_ready"] = False
        report["production_ready_100pct"] = False
        report["status"] = report.get("status") or "NO_SIGNAL"
        report["signals_notified"] = 0
        pf_sum = report.get("paper_portfolio") or {}
        cycle = build_cycle_report(
            trading_date=trading_date, mode=mode, pf_summary=pf_sum, signal=None,
            exits=report.get("exits_today") or [], marks=marks, model_version=model_version,
            governor_action=str(report.get("governor_action") or ""),
            dq_status=str(report.get("dq_status") or ""),
            data_source=str(report.get("data_source") or ""),
            no_signal_reasons=["Tidak ada kandidat BUY top-1 yang lolos filter hari ini."],
            status=str(report.get("status") or "NO_SIGNAL"),
        )
        report["cycle_report"] = cycle.to_dict()
        try:
            text_msg, src, exec_obs = _telegram_text_from_cycle(cycle, report)
            report["telegram_composer_source"] = src
            report["executive_summary"] = exec_obs
        except Exception as e:
            text_msg = compose_telegram_message(cycle)
            src = "deterministic"
            report["telegram_composer_source"] = src
            report["executive_summary"] = {"error": type(e).__name__, "fallback_used": True}
        if allow_tg:
            provider = TelegramProvider.from_env()
            if provider is None:
                report["telegram_status"] = "TELEGRAM_DISABLED"
            else:
                try:
                    _send_plain(provider, text_msg)
                    report["telegram_status"] = "NO_SIGNAL_SENT"
                except Exception as e:
                    report["telegram_status"] = "NO_SIGNAL_SEND_FAILED"
                    report["telegram_error"] = type(e).__name__
        else:
            report["telegram_status"] = "NO_SIGNAL_SUPPRESSED"
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
        pf_sum = report.get("paper_portfolio") or {}
        top = to_send[0]
        shares = float(top.get("qty") or 0)
        if shares <= 0 and top.get("lots"):
            shares = shares_from_lots(float(top["lots"]))
        sig = build_buy_signal(
            signal_id=str(top.get("notification_id") or top.get("signal_id") or f"sig_{trading_date}_{top.get('symbol')}"),
            timestamp=trading_date, symbol=str(top["symbol"]),
            entry_reference=float(top.get("entry_price") or top.get("price") or 0),
            stop_loss=float(top.get("sl") or 0),
            tp1=float(top.get("tp1") or 0) or (float(top.get("entry_price") or top.get("price") or 0) + (float(top.get("tp") or 0) - float(top.get("entry_price") or top.get("price") or 0)) * 0.5),
            tp2=float(top.get("tp") or 0), shares=shares,
            equity=float(pf_sum.get("equity") or 0) or float(initial_capital),
            confidence=float(top.get("confidence") or 0), confidence_method="sma20_rank_score",
            model_version=model_version,
            explanation=[str(top.get("why") or "Ranking confidence vs SMA20")],
            entry_low=float(top.get("entry_price") or top.get("price") or 0) * 0.995,
            entry_high=float(top.get("entry_price") or top.get("price") or 0) * 1.0025,
            fill_status=str(top.get("fill_status") or ""),
        )
        if sig.tp1 <= 0 and sig.tp2 > 0 and sig.entry_reference > 0:
            sig.tp1 = sig.entry_reference + (sig.tp2 - sig.entry_reference) * 0.5
        cycle = build_cycle_report(
            trading_date=trading_date, mode=mode, pf_summary=pf_sum, signal=sig,
            exits=report.get("exits_today") or [], marks=marks, model_version=model_version,
            governor_action=str(report.get("governor_action") or ""),
            dq_status=str(report.get("dq_status") or ""),
            data_source=str(report.get("data_source") or ""),
            status=str(report.get("status") or "SUCCESS"),
        )
        report["cycle_report"] = cycle.to_dict()
        report["integrity_ok"] = cycle.integrity_ok
        report["integrity_errors"] = cycle.integrity_errors
        try:
            text, src, exec_obs = _telegram_text_from_cycle(cycle, report)
            report["telegram_composer_source"] = src
            report["executive_summary"] = exec_obs
        except Exception as e:
            text = compose_telegram_message(cycle)
            src = "deterministic"
            report["telegram_composer_source"] = src
            report["executive_summary"] = {"error": type(e).__name__, "fallback_used": True}
        try:
            _send_plain(provider, text)
            for s in to_send:
                nstore.mark(s["notification_id"], "NOTIFIED", {"trading_date": trading_date}); notified += 1
            tg_status = "SENT" if cycle.integrity_ok else "SENT_INTEGRITY_WARNING"
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
