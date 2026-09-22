"""Instant Paper Portfolio — simulated fills only, NO broker execution.

Schema ops_paper_v2 + TP/SL + performance metrics + ledger reconstruction.
NO LIVE EXECUTION. Broker is never used for orders.

ACCOUNTING DEFINITIONS (SSOT — single definition per field)
----------------------------------------------------------
initial_capital   : starting cash of the simulation session
cash              : free cash after fees and fills
market_value      : sum(qty * current_market_price) for open positions
cost_basis_open   : sum(qty * avg_entry) for open positions  (= Modal Posisi)
equity            : cash + market_value                      (identity, always)
realized_pnl      : cumulative P&L from closed trades
                    (proceeds - cost_basis of sold qty; fees already in proceeds)
position_unrealized_pnl (= unrealized_pnl):
                    market_value - cost_basis_open
                    = sum(qty * (mark - avg_entry))
equity_pnl        : equity - initial_capital
total_trading_pnl : realized_pnl + position_unrealized_pnl
fees / slippage   : transaction costs; fees are cash-only (not in avg_entry);
                    slippage is embedded in fill_price / avg_entry

Do NOT mix equity_pnl with position unrealized without labels.
avg_entry includes entry slippage; fee does NOT enter avg_entry.
"""
from __future__ import annotations
import hashlib, json, uuid, re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = "ops_paper_v2"
DEFAULT_INITIAL_CAPITAL = 10_000_000.0
try:
    from src.python.reporting.finance import SHARES_PER_LOT as DEFAULT_LOT_SIZE
except Exception:
    DEFAULT_LOT_SIZE = 100.0  # 1 lot = 100 shares
DEFAULT_SL_PCT = 0.03
DEFAULT_TP_PCT = 0.06

# Simulation assumptions (NOT real broker fee schedule)
SIM_FEE_BUY_BPS = 15.0
SIM_FEE_EXIT_BPS = 25.0
SIM_SLIPPAGE_BPS = 5.0
SIM_FEE_MODEL = "SIMULATION"
INTRABAR_POLICY = "SL_PRECEDENCE"  # when both TP and SL touch same bar; assumption, not fact


def simulation_assumptions() -> dict:
    """Explicit fee/slippage/intrabar policy for reports and audits."""
    return {
        "fee_model": SIM_FEE_MODEL,
        "buy_fee_bps": SIM_FEE_BUY_BPS,
        "exit_fee_bps": SIM_FEE_EXIT_BPS,
        "slippage_bps": SIM_SLIPPAGE_BPS,
        "intrabar_policy": INTRABAR_POLICY,
        "note": "Fee/slippage are simulation assumptions, not broker fact.",
    }


PROTECTED_FROM_PAPER_RESET = (
    "models/", "state/training_runs/", "state/governor/", "state/learning/",
    "state/calibration/", "state/ops/shadow/", "artifacts/real_idx_oos/", "src/python/",
)


def paper_reset_scope() -> dict:
    return {
        "resets": "PAPER_ACCOUNT_STATE_ONLY",
        "fields": ["simulation_session_id", "cash", "positions", "equity", "realized_pnl", "drawdown"],
        "preserved": [
            "ML models and weights", "calibration", "online/adaptive learning",
            "Governor evidence/history", "shadow challenger evidence", "research/OOS evidence",
            "strategy config", "risk config", "production model pointer",
        ],
        "does_not": [
            "retrain", "delete models", "clear calibration", "clear learner",
            "clear performance history", "change production pointer", "change strategy",
            "change Governor policy",
        ],
        "protected_path_prefixes": list(PROTECTED_FROM_PAPER_RESET),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class PaperPosition:
    symbol: str
    qty: float
    avg_entry: float
    entry_timestamp: str
    signal_id: str = ""
    side: int = 1
    last_mark: float = 0.0
    tp: float = 0.0
    sl: float = 0.0
    # Adaptive exit state (optional; defaults keep static 3%/6% behavior)
    peak_mark: float = 0.0
    time_stop_bars: int = 0  # 0 = disabled
    trailing_pct: float = 0.0  # 0 = disabled; e.g. 0.03 = trail 3% from peak
    exit_method: str = "static_pct"

    def market_value(self, mark: Optional[float] = None) -> float:
        m = float(mark if mark is not None else self.last_mark or self.avg_entry)
        return float(self.qty) * m

    def cost_basis(self) -> float:
        """Modal posisi = qty × avg_entry (avg_entry includes entry slippage, excludes fee)."""
        return float(self.qty) * float(self.avg_entry)

    def lots(self) -> float:
        return float(self.qty) / DEFAULT_LOT_SIZE

    def unrealized_pnl(self, mark: Optional[float] = None) -> float:
        """Position unrealized = qty × (mark − avg_entry). Does NOT include entry fee."""
        m = float(mark if mark is not None else self.last_mark or self.avg_entry)
        return float(self.qty) * (m - float(self.avg_entry))


@dataclass
class PaperPortfolioState:
    simulation_session_id: str
    initial_capital: float = DEFAULT_INITIAL_CAPITAL
    cash: float = DEFAULT_INITIAL_CAPITAL
    positions: dict = field(default_factory=dict)
    realized_pnl: float = 0.0
    peak_equity: float = DEFAULT_INITIAL_CAPITAL
    max_drawdown: float = 0.0
    trade_count: int = 0
    signal_count: int = 0
    last_processed_trading_day: str = ""
    last_event: str = ""
    schema_version: str = SCHEMA_VERSION
    strategy_version: str = "idx_v1"
    model_version: str = ""
    created_at: str = ""
    updated_at: str = ""
    applied_order_ids: list = field(default_factory=list)
    trades: list = field(default_factory=list)
    equity_ledger: list = field(default_factory=list)
    signal_ledger: list = field(default_factory=list)
    checksum: str = ""

    def open_positions(self) -> dict[str, PaperPosition]:
        out = {}
        for k, v in (self.positions or {}).items():
            p = (
                PaperPosition(**{kk: vv for kk, vv in v.items() if kk in PaperPosition.__dataclass_fields__})
                if isinstance(v, dict) else v
            )
            if p.qty > 0:
                out[k] = p
        return out

    def market_value(self, marks: Optional[dict[str, float]] = None) -> float:
        marks = marks or {}
        return sum(p.market_value(marks.get(sym)) for sym, p in self.open_positions().items())

    def cost_basis_open(self) -> float:
        return sum(p.cost_basis() for p in self.open_positions().values())

    def position_unrealized_pnl(self, marks: Optional[dict[str, float]] = None) -> float:
        marks = marks or {}
        return sum(p.unrealized_pnl(marks.get(sym)) for sym, p in self.open_positions().items())

    def equity(self, marks: Optional[dict[str, float]] = None) -> float:
        """SSOT identity: equity = cash + market_value."""
        return float(self.cash) + self.market_value(marks)

    def exposure(self, marks: Optional[dict[str, float]] = None) -> float:
        eq = self.equity(marks)
        return 0.0 if eq <= 0 else self.market_value(marks) / eq

    def drawdown(self, marks: Optional[dict[str, float]] = None) -> float:
        eq = self.equity(marks)
        return 0.0 if self.peak_equity <= 0 else max(0.0, (self.peak_equity - eq) / self.peak_equity)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        payload = {k: v for k, v in d.items() if k != "checksum"}
        d["checksum"] = _sha(payload)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PaperPortfolioState":
        known = set(cls.__dataclass_fields__)
        positions = d.get("positions") or {}
        for sym, pdict in list(positions.items()):
            if isinstance(pdict, dict):
                pdict.setdefault("tp", 0.0)
                pdict.setdefault("sl", 0.0)
                positions[sym] = pdict
        d = dict(d)
        d["positions"] = positions
        d["schema_version"] = SCHEMA_VERSION
        return cls(**{k: v for k, v in d.items() if k in known})

    def verify_checksum(self) -> bool:
        d = asdict(self)
        payload = {k: v for k, v in d.items() if k != "checksum"}
        return self.checksum == _sha(payload)


def new_session(initial_capital: float = DEFAULT_INITIAL_CAPITAL, model_version: str = "") -> PaperPortfolioState:
    sid = f"SIM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now = _utc_now()
    st = PaperPortfolioState(
        simulation_session_id=sid,
        initial_capital=float(initial_capital),
        cash=float(initial_capital),
        peak_equity=float(initial_capital),
        model_version=model_version,
        created_at=now,
        updated_at=now,
    )
    st.checksum = st.to_dict()["checksum"]
    return st


class PaperPortfolioStore:
    def __init__(self, path: Path | str, archive_dir: Optional[Path | str] = None):
        self.path = Path(path)
        self.archive_dir = Path(archive_dir) if archive_dir else self.path.parent / "sessions"

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> PaperPortfolioState:
        raw = json.loads(self.path.read_text())
        st = PaperPortfolioState.from_dict(raw)
        if st.schema_version not in (SCHEMA_VERSION, "ops_paper_v1"):
            raise ValueError(f"schema_mismatch:{st.schema_version}")
        if st.checksum and not st.verify_checksum():
            st.checksum = st.to_dict()["checksum"]
        if st.cash < -1e-6:
            raise ValueError("negative_cash_corrupt")
        return st

    def save_atomic(self, state: PaperPortfolioState) -> None:
        state.updated_at = _utc_now()
        state.schema_version = SCHEMA_VERSION
        payload = state.to_dict()
        state.checksum = payload["checksum"]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, default=str))
        st2 = PaperPortfolioState.from_dict(json.loads(tmp.read_text()))
        if not st2.verify_checksum():
            tmp.unlink(missing_ok=True)
            raise RuntimeError("persist_validation_failed")
        tmp.replace(self.path)

    def archive_and_reset(
        self, *, initial_capital: float = DEFAULT_INITIAL_CAPITAL, model_version: str = ""
    ):
        old = None
        if self.path.exists():
            try:
                old = self.load()
            except Exception:
                old = None
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            dest = self.archive_dir / f"archived_{stamp}_{self.path.name}"
            if self.path.exists():
                dest.write_text(self.path.read_text())
        new = new_session(initial_capital=initial_capital, model_version=model_version)
        self.save_atomic(new)
        return old or new_session(initial_capital=0.0), new


def compute_tp_sl(entry: float, *, sl_pct: float = DEFAULT_SL_PCT, tp_pct: float = DEFAULT_TP_PCT):
    entry = float(entry)
    if entry <= 0:
        return 0.0, 0.0
    return round(entry * (1.0 + tp_pct), 2), round(entry * (1.0 - sl_pct), 2)


def apply_long_entry(
    state: PaperPortfolioState,
    *,
    symbol: str,
    price: float,
    weight: float,
    signal_id: str,
    timestamp: str,
    lot_size: float = DEFAULT_LOT_SIZE,
    fee_bps: float = SIM_FEE_BUY_BPS,
    slippage_bps: float = SIM_SLIPPAGE_BPS,
    tp: Optional[float] = None,
    sl: Optional[float] = None,
    allow_scale_in: bool = False,
    min_reentry_days: int = 0,
    time_stop_bars: int = 0,
    trailing_pct: float = 0.0,
    exit_method: str = "static_pct",
    market_gate=None,
    enforce_market_gate: bool = False,
    order_qty: Optional[float] = None,
):
    """Paper long entry. When enforce_market_gate=True, market_gate is mandatory authority."""
    if enforce_market_gate:
        if market_gate is None:
            return state, None, "SKIPPED_MS_MISSING_GATE"
        try:
            from src.python.market_structure import OrderRequest
            from src.python.ops.execution_authority import block_status_code, clear_for_execution
            approx_qty = int(order_qty or lot_size)
            if approx_qty < int(lot_size):
                approx_qty = int(lot_size)
            req = OrderRequest(symbol=symbol, side=1, price=float(price), quantity=approx_qty, signal_id=signal_id)
            _vo, ms = clear_for_execution(market_gate, req)
            if _vo is None:
                return state, None, block_status_code(ms)
        except Exception:
            return state, None, "SKIPPED_MS_GATE_ERROR"
    order = f"{signal_id}|BUY|{symbol}"
    oid = "ord_" + hashlib.sha256(order.encode()).hexdigest()[:16]
    if oid in set(state.applied_order_ids):
        return state, None, "ALREADY_APPLIED"
    existing = state.open_positions().get(symbol)
    if existing is not None and not allow_scale_in:
        return state, None, "SKIPPED_EXISTING_POSITION"
    if min_reentry_days > 0 and existing is None:
        last_exit_ts = None
        for tr in reversed(state.trades or []):
            if str(tr.get("symbol")) == symbol and str(tr.get("action", "")).upper() in ("SELL", "EXIT"):
                last_exit_ts = str(tr.get("timestamp") or "")
                break
        if last_exit_ts and len(str(timestamp)) >= 10 and len(last_exit_ts) >= 10:
            try:
                from datetime import datetime as _dt
                t_now = _dt.strptime(str(timestamp)[:10], "%Y-%m-%d")
                t_ex = _dt.strptime(last_exit_ts[:10], "%Y-%m-%d")
                if (t_now - t_ex).days < int(min_reentry_days):
                    return state, None, "SKIPPED_COOLDOWN"
            except Exception:
                pass
    if price <= 0 or weight <= 0:
        return state, None, "SKIPPED_INVALID_DATA"
    equity = state.equity({symbol: price})
    notional_target = equity * min(weight, 0.25)
    exec_px = price * (1.0 + slippage_bps / 10000.0)
    qty = (notional_target / exec_px) // lot_size * lot_size
    if qty < lot_size:
        return state, None, "SKIPPED_CASH"
    notional = qty * exec_px
    fee = notional * (fee_bps / 10000.0)
    cost = notional + fee
    if cost > state.cash + 1e-6:
        return state, None, "SKIPPED_CASH"
    state.cash -= cost
    if state.cash < -1e-6:
        state.cash += cost
        return state, None, "SKIPPED_CASH"
    if tp is None or sl is None or tp <= 0 or sl <= 0:
        tp, sl = compute_tp_sl(exec_px)
    if existing:
        total_qty = float(existing.qty) + float(qty)
        avg = (float(existing.qty) * float(existing.avg_entry) + float(qty) * float(exec_px)) / total_qty
        pos = PaperPosition(
            symbol=symbol,
            qty=total_qty,
            avg_entry=float(avg),
            entry_timestamp=existing.entry_timestamp or timestamp,
            signal_id=signal_id,
            side=1,
            last_mark=float(exec_px),
            tp=float(tp if tp else existing.tp),
            sl=float(sl if sl else existing.sl),
            peak_mark=max(float(existing.peak_mark or 0), float(exec_px)),
            time_stop_bars=int(time_stop_bars or existing.time_stop_bars or 0),
            trailing_pct=float(trailing_pct or existing.trailing_pct or 0),
            exit_method=str(exit_method or existing.exit_method or "static_pct"),
        )
    else:
        pos = PaperPosition(
            symbol=symbol,
            qty=float(qty),
            avg_entry=float(exec_px),
            entry_timestamp=timestamp,
            signal_id=signal_id,
            side=1,
            last_mark=float(exec_px),
            tp=float(tp),
            sl=float(sl),
            peak_mark=float(exec_px),
            time_stop_bars=int(time_stop_bars or 0),
            trailing_pct=float(trailing_pct or 0),
            exit_method=str(exit_method or "static_pct"),
        )
    state.positions[symbol] = asdict(pos)
    state.applied_order_ids = (state.applied_order_ids + [oid])[-5000:]
    state.trade_count += 1
    state.signal_count += 1
    trade = {
        "trade_id": "tx_" + hashlib.sha256(f"{oid}|0".encode()).hexdigest()[:16],
        "order_id": oid,
        "signal_id": signal_id,
        "symbol": symbol,
        "side": 1,
        "action": "BUY",
        "qty": float(qty),
        "lots": float(qty) / lot_size,
        "reference_price": float(price),
        "fill_price": float(exec_px),
        "price": float(exec_px),
        "gross_value": float(notional),
        "notional": float(notional),
        "fee": float(fee),
        "fee_bps": float(fee_bps),
        "slippage_bps": float(slippage_bps),
        "total_cost": float(cost),
        "net_cash_change": float(-cost),
        "cost_basis": float(qty) * float(exec_px),
        "tp": float(tp),
        "sl": float(sl),
        "timestamp": timestamp,
        "status": "FILLED",
        "classification": "PAPER_FILLED",
        "scale_in": bool(existing is not None),
        "position_qty_after": float(pos.qty),
        "position_avg_entry_after": float(pos.avg_entry),
        "position_lots_after": float(pos.qty) / float(lot_size),
    }
    state.trades = (state.trades + [trade])[-2000:]
    state.signal_ledger = (
        state.signal_ledger
        + [{"signal_id": signal_id, "symbol": symbol, "side": "BUY", "status": "PAPER_FILLED", "timestamp": timestamp}]
    )[-2000:]
    state.last_event = f"BUY {symbol} qty={qty} lots={qty / lot_size:.0f} tp={tp} sl={sl}"
    _update_equity_snapshot(state, {symbol: exec_px}, timestamp)
    return state, trade, "PAPER_FILLED"


def apply_exit(
    state: PaperPortfolioState,
    *,
    symbol: str,
    price: float,
    timestamp: str,
    reason: str = "MANUAL",
    fee_bps: float = SIM_FEE_EXIT_BPS,
    slippage_bps: float = SIM_SLIPPAGE_BPS,
):
    open_pos = state.open_positions()
    if symbol not in open_pos:
        return state, None, "NO_POSITION"
    pos = open_pos[symbol]
    if pos.qty <= 0:
        return state, None, "NO_POSITION"
    exec_px = float(price) * (1.0 - slippage_bps / 10000.0)
    if exec_px <= 0:
        return state, None, "SKIPPED_INVALID_DATA"
    notional = float(pos.qty) * exec_px
    fee = notional * (fee_bps / 10000.0)
    proceeds = notional - fee
    cost_basis = float(pos.qty) * float(pos.avg_entry)
    pnl = proceeds - cost_basis
    state.cash += proceeds
    state.realized_pnl += pnl
    state.trade_count += 1
    order = f"EXIT|{symbol}|{timestamp}|{reason}"
    oid = "ord_" + hashlib.sha256(order.encode()).hexdigest()[:16]
    trade = {
        "trade_id": "tx_" + hashlib.sha256(f"{oid}|exit".encode()).hexdigest()[:16],
        "order_id": oid,
        "signal_id": pos.signal_id,
        "symbol": symbol,
        "side": -1,
        "action": "SELL",
        "qty": float(pos.qty),
        "lots": float(pos.qty) / DEFAULT_LOT_SIZE,
        "reference_price": float(price),
        "fill_price": float(exec_px),
        "price": float(exec_px),
        "gross_value": float(notional),
        "notional": float(notional),
        "fee": float(fee),
        "fee_bps": float(fee_bps),
        "slippage_bps": float(slippage_bps),
        "proceeds": float(proceeds),
        "net_cash_change": float(proceeds),
        "pnl": float(pnl),
        "cost_basis": float(cost_basis),
        "reason": reason,
        "entry": float(pos.avg_entry),
        "tp": float(pos.tp or 0),
        "sl": float(pos.sl or 0),
        "timestamp": timestamp,
        "status": "FILLED",
        "classification": "FULL_EXIT",
    }
    state.trades = (state.trades + [trade])[-2000:]
    state.signal_ledger = (
        state.signal_ledger
        + [{"signal_id": pos.signal_id, "symbol": symbol, "side": "SELL", "status": reason, "timestamp": timestamp}]
    )[-2000:]
    del state.positions[symbol]
    state.last_event = f"EXIT {symbol} reason={reason} pnl={pnl:.0f}"
    _update_equity_snapshot(state, {symbol: exec_px}, timestamp)
    return state, trade, reason


def process_tp_sl_exits(
    state: PaperPortfolioState,
    marks: dict[str, float],
    timestamp: str,
    *,
    fee_bps: float = SIM_FEE_EXIT_BPS,
    slippage_bps: float = SIM_SLIPPAGE_BPS,
):
    """Evaluate exits: SL / TP / trailing stop / time-stop (calendar days ≈ bars).

    Priority (fail-closed, conservative):
      1. SL_HIT (static or trailed stop)
      2. TP_HIT
      3. TIME_STOP (if time_stop_bars > 0 and days held >= limit)
    Trailing ratchets SL up with peak_mark; never loosens stop.
    """
    closed = []
    for sym, pos in list(state.open_positions().items()):
        mark = marks.get(sym)
        if mark is None or mark <= 0:
            continue
        mark = float(mark)
        # Update peak + optional trailing ratchet on live position dict
        pdict = state.positions.get(sym)
        if isinstance(pdict, dict):
            peak = max(float(pdict.get("peak_mark") or 0), float(pos.peak_mark or 0), mark)
            pdict["peak_mark"] = peak
            pdict["last_mark"] = mark
            trail = float(pdict.get("trailing_pct") or pos.trailing_pct or 0)
            if trail > 0 and peak > 0:
                trailed_sl = peak * (1.0 - trail)
                cur_sl = float(pdict.get("sl") or pos.sl or 0)
                # only tighten (raise) stop for long
                if trailed_sl > cur_sl:
                    pdict["sl"] = round(trailed_sl, 2)
            state.positions[sym] = pdict
            pos = state.open_positions()[sym]

        reason = None
        exit_px = mark
        if pos.sl and pos.sl > 0 and mark <= pos.sl:
            reason = "SL_HIT"
            exit_px = min(mark, float(pos.sl))
        elif pos.tp and pos.tp > 0 and mark >= pos.tp:
            reason = "TP_HIT"
            exit_px = max(mark, float(pos.tp))
        else:
            # time-stop: calendar-day distance from entry_timestamp
            tsb = int(pos.time_stop_bars or 0)
            if tsb > 0 and pos.entry_timestamp and len(str(timestamp)) >= 10 and len(str(pos.entry_timestamp)) >= 10:
                try:
                    from datetime import datetime as _dt
                    t_now = _dt.strptime(str(timestamp)[:10], "%Y-%m-%d")
                    t_en = _dt.strptime(str(pos.entry_timestamp)[:10], "%Y-%m-%d")
                    held = (t_now - t_en).days
                    if held >= tsb:
                        reason = "TIME_STOP"
                        exit_px = mark
                except Exception:
                    pass
        if reason:
            state, trade, cls = apply_exit(
                state, symbol=sym, price=exit_px, timestamp=timestamp,
                reason=reason, fee_bps=fee_bps, slippage_bps=slippage_bps,
            )
            if trade:
                trade["exit_method"] = pos.exit_method
                closed.append(trade)
    return state, closed


def mark_to_market(
    state: PaperPortfolioState, marks: dict[str, float], timestamp: str
) -> PaperPortfolioState:
    for sym, pdict in list(state.positions.items()):
        if sym in marks and isinstance(pdict, dict) and pdict.get("qty", 0) > 0:
            pdict["last_mark"] = float(marks[sym])
            state.positions[sym] = pdict
    _update_equity_snapshot(state, marks, timestamp)
    return state


def _update_equity_snapshot(
    state: PaperPortfolioState, marks: dict[str, float], timestamp: str
) -> None:
    eq = state.equity(marks)
    if eq > state.peak_equity:
        state.peak_equity = eq
    dd = state.drawdown(marks)
    if dd > state.max_drawdown:
        state.max_drawdown = dd
    state.equity_ledger = (
        state.equity_ledger
        + [{
            "timestamp": timestamp,
            "cash": state.cash,
            "market_value": state.market_value(marks),
            "cost_basis_open": state.cost_basis_open(),
            "equity": eq,
            "exposure": state.exposure(marks),
            "realized_pnl": state.realized_pnl,
            "position_unrealized_pnl": state.position_unrealized_pnl(marks),
            "equity_pnl": eq - float(state.initial_capital),
            "drawdown": dd,
        }]
    )[-5000:]


def position_detail(pos: PaperPosition, mark: Optional[float] = None) -> dict[str, Any]:
    m = float(mark if mark is not None else pos.last_mark or pos.avg_entry)
    upnl = pos.unrealized_pnl(m)
    cb = pos.cost_basis()
    return {
        "symbol": pos.symbol,
        "qty": pos.qty,
        "lots": pos.lots(),
        "avg_entry": pos.avg_entry,
        "cost_basis": cb,
        "last_mark": m,
        "market_value": pos.market_value(m),
        "unrealized_pnl": upnl,
        "unrealized_pnl_pct": (upnl / cb * 100.0) if cb else 0.0,
        "tp": pos.tp,
        "sl": pos.sl,
        "dist_tp_pct": ((pos.tp - m) / m * 100.0) if m and pos.tp else None,
        "dist_sl_pct": ((m - pos.sl) / m * 100.0) if m and pos.sl else None,
        "entry_timestamp": pos.entry_timestamp,
        "signal_id": pos.signal_id,
    }


def summary(state: PaperPortfolioState, marks: Optional[dict[str, float]] = None) -> dict[str, Any]:
    """Portfolio summary with explicit, non-mixed P&L definitions."""
    marks = marks or {}
    open_pos = state.open_positions()
    open_det = {k: position_detail(v, marks.get(k)) for k, v in open_pos.items()}
    mv = state.market_value(marks)
    eq = state.equity(marks)
    cb = state.cost_basis_open()
    pos_upnl = state.position_unrealized_pnl(marks)
    equity_pnl = eq - float(state.initial_capital)
    return {
        "simulation_session_id": state.simulation_session_id,
        "initial_capital": state.initial_capital,
        "cash": state.cash,
        "equity": eq,
        "market_value": mv,
        "cost_basis_open": cb,
        "exposure": state.exposure(marks),
        "realized_pnl": state.realized_pnl,
        "unrealized_pnl": pos_upnl,  # position price only
        "equity_pnl": equity_pnl,    # equity - initial
        "total_trading_pnl": float(state.realized_pnl) + pos_upnl,
        "peak_equity": state.peak_equity,
        "drawdown": state.drawdown(marks),
        "max_drawdown": state.max_drawdown,
        "open_positions": open_det,
        "open_count": len(open_det),
        "trade_count": state.trade_count,
        "signal_count": state.signal_count,
        "last_processed_trading_day": state.last_processed_trading_day,
        "last_event": state.last_event,
        "schema_version": state.schema_version,
        "simulation": simulation_assumptions(),
        "accounting_note": (
            "unrealized_pnl = sum qty*(mark-avg_entry); "
            "equity_pnl = equity-initial_capital; "
            "fees are cash-only and appear in equity_pnl, not in position unrealized"
        ),
    }


def performance_metrics(
    state: PaperPortfolioState, marks: Optional[dict[str, float]] = None
) -> dict[str, Any]:
    """Compute performance from ledger. N/A when sample insufficient — no fake metrics."""
    marks = marks or {}
    closed = [
        t for t in (state.trades or [])
        if str(t.get("action") or "").upper() == "SELL" or int(t.get("side") or 0) < 0
    ]
    wins = [t for t in closed if float(t.get("pnl") or 0) > 0]
    losses = [t for t in closed if float(t.get("pnl") or 0) < 0]
    gross_profit = sum(float(t.get("pnl") or 0) for t in wins)
    gross_loss = abs(sum(float(t.get("pnl") or 0) for t in losses))
    total_fees = sum(float(t.get("fee") or 0) for t in (state.trades or []))
    total_slip = 0.0
    for t in state.trades or []:
        bps = float(t.get("slippage_bps") or 0)
        notion = float(t.get("notional") or t.get("gross_value") or 0)
        total_slip += notion * (bps / 10000.0)
    eq = state.equity(marks)
    pos_upnl = state.position_unrealized_pnl(marks)
    equity_pnl = eq - float(state.initial_capital)
    n_closed = len(closed)
    out: dict[str, Any] = {
        "initial_capital": float(state.initial_capital),
        "current_equity": float(eq),
        "cash": float(state.cash),
        "market_value": float(state.market_value(marks)),
        "cost_basis_open": float(state.cost_basis_open()),
        "total_return_pct": (equity_pnl / state.initial_capital * 100.0) if state.initial_capital else 0.0,
        "realized_pnl": float(state.realized_pnl),
        "unrealized_pnl": float(pos_upnl),
        "equity_pnl": float(equity_pnl),
        "total_trading_pnl": float(state.realized_pnl) + float(pos_upnl),
        "total_pnl": float(equity_pnl),
        "number_of_trades": int(state.trade_count),
        "closed_trades": n_closed,
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "gross_profit": float(gross_profit),
        "gross_loss": float(gross_loss),
        "total_fees": float(total_fees),
        "total_slippage_est": float(total_slip),
        "exposure_pct": float(state.exposure(marks) * 100.0),
        "cash_ratio_pct": (state.cash / eq * 100.0) if eq > 0 else 100.0,
        "max_drawdown_pct": float(state.max_drawdown * 100.0),
        "current_drawdown_pct": float(state.drawdown(marks) * 100.0),
        "peak_equity": float(state.peak_equity),
    }
    if n_closed == 0:
        out["win_rate"] = None
        out["profit_factor"] = None
        out["expectancy"] = None
        out["average_win"] = None
        out["average_loss"] = None
        out["sample_note"] = "N/A — belum ada closed trade"
    else:
        out["win_rate"] = len(wins) / n_closed
        out["average_win"] = (gross_profit / len(wins)) if wins else 0.0
        out["average_loss"] = (gross_loss / len(losses)) if losses else 0.0
        out["profit_factor"] = (gross_profit / gross_loss) if gross_loss > 1e-9 else None
        out["expectancy"] = sum(float(t.get("pnl") or 0) for t in closed) / n_closed
        out["sample_note"] = None
    out["simulation"] = simulation_assumptions()
    return out


def rebuild_portfolio_from_trades(
    trades: list[dict[str, Any]],
    *,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    simulation_session_id: str = "",
) -> PaperPortfolioState:
    """Reconstruct portfolio state from append-only trade ledger (deterministic)."""
    st = new_session(initial_capital=initial_capital)
    if simulation_session_id:
        st.simulation_session_id = simulation_session_id
    for tr in trades:
        action = str(tr.get("action") or "").upper()
        side = int(tr.get("side") or 0)
        sym = str(tr.get("symbol") or "")
        qty = float(tr.get("qty") or 0)
        px = float(tr.get("fill_price") or tr.get("price") or 0)
        fee = float(tr.get("fee") or 0)
        ts = str(tr.get("timestamp") or "")
        if not sym or qty <= 0 or px <= 0:
            continue
        if action == "BUY" or side > 0:
            cost = qty * px + fee
            st.cash -= cost
            existing = st.open_positions().get(sym)
            if existing:
                total_qty = existing.qty + qty
                avg = (existing.qty * existing.avg_entry + qty * px) / total_qty if total_qty else px
                st.positions[sym] = asdict(PaperPosition(
                    symbol=sym, qty=total_qty, avg_entry=avg,
                    entry_timestamp=existing.entry_timestamp or ts,
                    signal_id=str(tr.get("signal_id") or existing.signal_id),
                    side=1, last_mark=px,
                    tp=float(tr.get("tp") or existing.tp or 0),
                    sl=float(tr.get("sl") or existing.sl or 0),
                ))
            else:
                st.positions[sym] = asdict(PaperPosition(
                    symbol=sym, qty=qty, avg_entry=px, entry_timestamp=ts,
                    signal_id=str(tr.get("signal_id") or ""), side=1, last_mark=px,
                    tp=float(tr.get("tp") or 0), sl=float(tr.get("sl") or 0),
                ))
            st.trade_count += 1
        elif action == "SELL" or side < 0:
            existing = st.open_positions().get(sym)
            if not existing:
                continue
            sell_qty = min(qty, existing.qty)
            proceeds = sell_qty * px - fee
            cost_basis = sell_qty * existing.avg_entry
            st.cash += proceeds
            st.realized_pnl += proceeds - cost_basis
            remaining = existing.qty - sell_qty
            if remaining <= 1e-9:
                del st.positions[sym]
            else:
                st.positions[sym] = asdict(PaperPosition(
                    symbol=sym, qty=remaining, avg_entry=existing.avg_entry,
                    entry_timestamp=existing.entry_timestamp, signal_id=existing.signal_id,
                    side=1, last_mark=px, tp=existing.tp, sl=existing.sl,
                ))
            st.trade_count += 1
        st.trades.append(dict(tr))
    return st


def validate_portfolio_accounting(
    state: PaperPortfolioState, marks: Optional[dict[str, float]] = None
) -> list[str]:
    """Detect accounting anomalies — never silent-correct."""
    marks = marks or {}
    errs: list[str] = []
    if state.cash < -1e-4:
        errs.append(f"negative_cash:{state.cash}")
    mv = state.market_value(marks)
    eq = state.equity(marks)
    if abs(eq - (state.cash + mv)) > 1.0:
        errs.append(f"equity_mismatch cash+mv={state.cash + mv} equity={eq}")
    for sym, pos in state.open_positions().items():
        if pos.qty < -1e-9:
            errs.append(f"negative_qty:{sym}")
        if pos.qty == 0:
            errs.append(f"phantom_zero_position:{sym}")
    ids = [t.get("trade_id") for t in (state.trades or []) if t.get("trade_id")]
    if len(ids) != len(set(ids)):
        errs.append("duplicate_trade_id")
    return errs


def process_tp_sl_exits_ohlc(
    state: PaperPortfolioState,
    bars: dict[str, dict[str, float]],
    timestamp: str,
    *,
    fee_bps: float = SIM_FEE_EXIT_BPS,
    slippage_bps: float = SIM_SLIPPAGE_BPS,
) -> tuple:
    """Intrabar TP/SL using high/low. Conservative: if both hit same bar, SL takes precedence."""
    closed = []
    for sym, pos in list(state.open_positions().items()):
        bar = bars.get(sym) or {}
        high = float(bar.get("high") or 0)
        low = float(bar.get("low") or 0)
        close = float(bar.get("close") or 0)
        if high <= 0 and low <= 0 and close <= 0:
            continue
        if high <= 0:
            high = close
        if low <= 0:
            low = close
        reason = None
        exit_px = close
        sl_hit = bool(pos.sl and pos.sl > 0 and low <= pos.sl)
        tp_hit = bool(pos.tp and pos.tp > 0 and high >= pos.tp)
        if sl_hit and tp_hit:
            reason = "SL_HIT"
            exit_px = float(pos.sl)
        elif sl_hit:
            reason = "SL_HIT"
            exit_px = float(pos.sl)
        elif tp_hit:
            reason = "TP_HIT"
            exit_px = float(pos.tp)
        if reason:
            state, trade, cls = apply_exit(
                state, symbol=sym, price=exit_px, timestamp=timestamp,
                reason=reason, fee_bps=fee_bps, slippage_bps=slippage_bps,
            )
            if trade:
                trade["intrabar_policy"] = INTRABAR_POLICY
                if sl_hit and tp_hit:
                    trade["intrabar_conflict"] = "BOTH_TOUCHED_SL_PRECEDENCE"
                closed.append(trade)
    return state, closed


def assert_no_broker_execution_imports(module_source: str) -> list[str]:
    """Static guard: paper module must not call broker order APIs."""
    patterns = [
        r"\bplace_order\s*\(",
        r"\bsubmit_order\s*\(",
        r"\bcreate_order\s*\(",
        r"\bsend_order\s*\(",
        r"BrokerClient\s*\.\s*execute",
        r"\blive_order\s*\(",
    ]
    hits = []
    for pat in patterns:
        if re.search(pat, module_source):
            hits.append(pat)
    return hits
