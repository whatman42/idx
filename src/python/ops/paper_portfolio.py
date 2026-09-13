"""Continuous operational paper portfolio — multi-day persistent, SIGNAL ONLY.
Default: Rp 10_000_000. Reset = PAPER ACCOUNT only (not models/learning/evidence).
"""
from __future__ import annotations
import hashlib, json, uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = "ops_paper_v1"
DEFAULT_INITIAL_CAPITAL = 10_000_000.0
PROTECTED_FROM_PAPER_RESET = ("models/", "state/training_runs/", "state/governor/", "state/learning/", "state/calibration/", "state/ops/shadow/", "artifacts/real_idx_oos/", "src/python/")

def paper_reset_scope() -> dict:
    return {"resets": "PAPER_ACCOUNT_STATE_ONLY",
            "fields": ["simulation_session_id", "cash", "positions", "equity", "realized_pnl", "drawdown"],
            "preserved": ["ML models and weights", "calibration", "online/adaptive learning", "Governor evidence/history", "shadow challenger evidence", "research/OOS evidence", "strategy config", "risk config", "production model pointer"],
            "does_not": ["retrain", "delete models", "clear calibration", "clear learner", "clear performance history", "change production pointer", "change strategy", "change Governor policy"],
            "protected_path_prefixes": list(PROTECTED_FROM_PAPER_RESET)}

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()

@dataclass
class PaperPosition:
    symbol: str; qty: float; avg_entry: float; entry_timestamp: str
    signal_id: str = ""; side: int = 1; last_mark: float = 0.0
    def market_value(self, mark: Optional[float] = None) -> float:
        m = float(mark if mark is not None else self.last_mark or self.avg_entry)
        return float(self.qty) * m

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
            p = PaperPosition(**{kk: vv for kk, vv in v.items() if kk in PaperPosition.__dataclass_fields__}) if isinstance(v, dict) else v
            if p.qty > 0: out[k] = p
        return out
    def market_value(self, marks: Optional[dict[str, float]] = None) -> float:
        marks = marks or {}
        return sum(p.market_value(marks.get(sym)) for sym, p in self.open_positions().items())
    def equity(self, marks: Optional[dict[str, float]] = None) -> float:
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
        return cls(**{k: v for k, v in d.items() if k in known})
    def verify_checksum(self) -> bool:
        d = asdict(self)
        payload = {k: v for k, v in d.items() if k != "checksum"}
        return self.checksum == _sha(payload)

def new_session(initial_capital: float = DEFAULT_INITIAL_CAPITAL, model_version: str = "") -> PaperPortfolioState:
    sid = f"SIM-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    now = _utc_now()
    st = PaperPortfolioState(simulation_session_id=sid, initial_capital=float(initial_capital),
        cash=float(initial_capital), peak_equity=float(initial_capital), model_version=model_version,
        created_at=now, updated_at=now)
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
        if st.schema_version != SCHEMA_VERSION:
            raise ValueError(f"schema_mismatch:{st.schema_version}")
        if st.checksum and not st.verify_checksum():
            raise ValueError("checksum_mismatch_corrupt_state")
        if st.cash < -1e-6:
            raise ValueError("negative_cash_corrupt")
        return st
    def save_atomic(self, state: PaperPortfolioState) -> None:
        state.updated_at = _utc_now()
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
    def archive_and_reset(self, *, initial_capital: float = DEFAULT_INITIAL_CAPITAL, model_version: str = "") -> tuple[PaperPortfolioState, PaperPortfolioState]:
        """Reset PAPER ACCOUNT only. Does NOT touch models/learning/evidence/pointer."""
        old: Optional[PaperPortfolioState] = None
        if self.path.exists():
            try: old = self.load()
            except Exception: old = None
            self.archive_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            dest = self.archive_dir / f"archived_{stamp}_{self.path.name}"
            if self.path.exists(): dest.write_text(self.path.read_text())
        new = new_session(initial_capital=initial_capital, model_version=model_version)
        self.save_atomic(new)
        return old or new_session(initial_capital=0.0), new

def apply_long_entry(state: PaperPortfolioState, *, symbol: str, price: float, weight: float,
    signal_id: str, timestamp: str, lot_size: float = 100.0, fee_bps: float = 15.0,
    slippage_bps: float = 5.0) -> tuple[PaperPortfolioState, Optional[dict], str]:
    order = f"{signal_id}|BUY|{symbol}"
    oid = "ord_" + hashlib.sha256(order.encode()).hexdigest()[:16]
    if oid in set(state.applied_order_ids): return state, None, "ALREADY_APPLIED"
    if symbol in state.open_positions(): return state, None, "SKIPPED_EXISTING_POSITION"
    if price <= 0 or weight <= 0: return state, None, "SKIPPED_INVALID_DATA"
    equity = state.equity({symbol: price})
    notional_target = equity * min(weight, 0.25)
    exec_px = price * (1.0 + slippage_bps / 10000.0)
    qty = (notional_target / exec_px) // lot_size * lot_size
    if qty < lot_size: return state, None, "SKIPPED_CASH"
    notional = qty * exec_px
    fee = notional * (fee_bps / 10000.0)
    cost = notional + fee
    if cost > state.cash + 1e-6: return state, None, "SKIPPED_CASH"
    state.cash -= cost
    if state.cash < -1e-6:
        state.cash += cost
        return state, None, "SKIPPED_CASH"
    pos = PaperPosition(symbol=symbol, qty=float(qty), avg_entry=float(exec_px),
        entry_timestamp=timestamp, signal_id=signal_id, side=1, last_mark=float(exec_px))
    state.positions[symbol] = asdict(pos)
    state.applied_order_ids = (state.applied_order_ids + [oid])[-5000:]
    state.trade_count += 1
    state.signal_count += 1
    trade = {"trade_id": "tx_" + hashlib.sha256(f"{oid}|0".encode()).hexdigest()[:16],
        "order_id": oid, "signal_id": signal_id, "symbol": symbol, "side": 1,
        "action": "BUY", "qty": float(qty), "price": float(exec_px), "fee": float(fee),
        "slippage_bps": slippage_bps, "timestamp": timestamp, "classification": "FULL_FILL"}
    state.trades = (state.trades + [trade])[-2000:]
    state.signal_ledger = (state.signal_ledger + [{"signal_id": signal_id, "symbol": symbol, "side": "BUY", "status": "FULL_FILL", "timestamp": timestamp}])[-2000:]
    state.last_event = f"BUY {symbol} qty={qty}"
    _update_equity_snapshot(state, {symbol: exec_px}, timestamp)
    return state, trade, "FULL_FILL"

def mark_to_market(state: PaperPortfolioState, marks: dict[str, float], timestamp: str) -> PaperPortfolioState:
    for sym, pdict in list(state.positions.items()):
        if sym in marks and isinstance(pdict, dict) and pdict.get("qty", 0) > 0:
            pdict["last_mark"] = float(marks[sym]); state.positions[sym] = pdict
    _update_equity_snapshot(state, marks, timestamp)
    return state

def _update_equity_snapshot(state: PaperPortfolioState, marks: dict[str, float], timestamp: str) -> None:
    eq = state.equity(marks)
    if eq > state.peak_equity: state.peak_equity = eq
    dd = state.drawdown(marks)
    if dd > state.max_drawdown: state.max_drawdown = dd
    state.equity_ledger = (state.equity_ledger + [{"timestamp": timestamp, "cash": state.cash, "market_value": state.market_value(marks), "equity": eq, "exposure": state.exposure(marks), "realized_pnl": state.realized_pnl, "drawdown": dd}])[-5000:]

def summary(state: PaperPortfolioState, marks: Optional[dict[str, float]] = None) -> dict[str, Any]:
    marks = marks or {}
    return {"simulation_session_id": state.simulation_session_id, "initial_capital": state.initial_capital, "cash": state.cash,
        "equity": state.equity(marks), "market_value": state.market_value(marks), "exposure": state.exposure(marks),
        "realized_pnl": state.realized_pnl, "unrealized_pnl": state.equity(marks) - state.initial_capital - state.realized_pnl,
        "peak_equity": state.peak_equity, "drawdown": state.drawdown(marks), "max_drawdown": state.max_drawdown,
        "open_positions": {k: asdict(v) for k, v in state.open_positions().items()},
        "trade_count": state.trade_count, "signal_count": state.signal_count,
        "last_processed_trading_day": state.last_processed_trading_day, "schema_version": state.schema_version}
