"""Crypto paper ledger SSOT — USDT base. Isolated from IDX paper_portfolio."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from src.python.crypto.config import (
    CRYPTO_BASE_CURRENCY,
    CRYPTO_FEE_BUY_BPS,
    CRYPTO_FEE_SELL_BPS,
    CRYPTO_INITIAL_CAPITAL_USDT,
    CRYPTO_SLIPPAGE_BPS,
    CRYPTO_STATE_PATH,
    assert_crypto_paper_only,
    crypto_sim_assumptions,
)

SCHEMA = "crypto_paper_v1"
EQUITY_TOL = 1e-6


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sid(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


@dataclass
class CryptoPosition:
    symbol: str
    qty: float
    avg_entry: float
    entry_timestamp: str
    signal_id: str = ""


@dataclass
class CryptoPaperLedger:
    """cash + market_value == equity (USDT)."""
    initial_capital: float = CRYPTO_INITIAL_CAPITAL_USDT
    cash: float = CRYPTO_INITIAL_CAPITAL_USDT
    positions: dict[str, CryptoPosition] = field(default_factory=dict)
    realized_pnl: float = 0.0
    fees_paid: float = 0.0
    fills: list[dict[str, Any]] = field(default_factory=list)
    applied_keys: set[str] = field(default_factory=set)
    session_id: str = ""
    schema: str = SCHEMA
    base_currency: str = CRYPTO_BASE_CURRENCY
    live_execution: bool = False

    def __post_init__(self):
        assert_crypto_paper_only()
        if not self.session_id:
            self.session_id = f"CRYPTO-SIM-{uuid.uuid4().hex[:8].upper()}"
        self.base_currency = CRYPTO_BASE_CURRENCY
        self.live_execution = False

    def market_value(self, marks: dict[str, float]) -> float:
        mv = 0.0
        for sym, p in self.positions.items():
            px = float(marks.get(sym, p.avg_entry))
            mv += p.qty * px
        return mv

    def equity(self, marks: dict[str, float]) -> float:
        return float(self.cash) + self.market_value(marks)

    def unrealized_pnl(self, marks: dict[str, float]) -> float:
        u = 0.0
        for sym, p in self.positions.items():
            px = float(marks.get(sym, p.avg_entry))
            u += p.qty * (px - p.avg_entry)
        return u

    def assert_invariant(self, marks: dict[str, float]) -> None:
        eq = self.equity(marks)
        expected = self.cash + self.market_value(marks)
        if abs(eq - expected) > EQUITY_TOL:
            raise RuntimeError(f"CRYPTO_LEDGER_INVARIANT: equity={eq} vs {expected}")

    def apply_buy(
        self,
        *,
        symbol: str,
        price: float,
        notional_usdt: float,
        signal_id: str,
        timestamp: str = "",
        min_qty: float = 0.0,
        min_notional: float = 0.0,
        qty_precision: int = 8,
    ) -> dict[str, Any]:
        assert_crypto_paper_only()
        key = _sid(signal_id, "BUY", symbol)
        if key in self.applied_keys:
            return {"status": "ALREADY_APPLIED", "key": key, "symbol": symbol}
        if notional_usdt <= 0 or price <= 0:
            return {"status": "REJECTED_INVALID", "symbol": symbol}
        if min_notional > 0 and notional_usdt < min_notional:
            return {"status": "REJECTED_MIN_NOTIONAL", "symbol": symbol}

        slip = price * (1.0 + CRYPTO_SLIPPAGE_BPS / 10_000.0)
        qty = notional_usdt / slip
        if qty_precision >= 0:
            factor = 10 ** qty_precision
            qty = int(qty * factor) / factor
        if min_qty > 0 and qty < min_qty:
            return {"status": "REJECTED_MIN_QTY", "symbol": symbol, "qty": qty}

        gross = qty * slip
        fee = gross * CRYPTO_FEE_BUY_BPS / 10_000.0
        total = gross + fee
        if total > self.cash + 1e-12:
            return {"status": "REJECTED_CASH", "symbol": symbol, "need": total, "cash": self.cash}

        self.cash -= total
        self.fees_paid += fee
        pos = self.positions.get(symbol)
        if pos is None:
            self.positions[symbol] = CryptoPosition(
                symbol=symbol, qty=qty, avg_entry=slip, entry_timestamp=timestamp or _utc(), signal_id=signal_id
            )
        else:
            new_qty = pos.qty + qty
            pos.avg_entry = (pos.avg_entry * pos.qty + slip * qty) / new_qty if new_qty else slip
            pos.qty = new_qty

        self.applied_keys.add(key)
        fill = {
            "status": "CRYPTO_PAPER_FILL",
            "side": "BUY",
            "symbol": symbol,
            "qty": qty,
            "price": slip,
            "fee": fee,
            "notional": gross,
            "signal_id": signal_id,
            "key": key,
            "timestamp": timestamp or _utc(),
            "broker": "NOT_SENT_NO_LIVE_EXECUTION",
            "base_currency": "USDT",
        }
        self.fills.append(fill)
        return fill

    def to_dict(self, marks: Optional[dict[str, float]] = None) -> dict[str, Any]:
        marks = marks or {s: p.avg_entry for s, p in self.positions.items()}
        self.assert_invariant(marks)
        return {
            "schema": self.schema,
            "session_id": self.session_id,
            "base_currency": self.base_currency,
            "live_execution": False,
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "market_value": self.market_value(marks),
            "equity": self.equity(marks),
            "realized_pnl": self.realized_pnl,
            "unrealized_pnl": self.unrealized_pnl(marks),
            "fees_paid": self.fees_paid,
            "positions": {k: asdict(v) for k, v in self.positions.items()},
            "n_fills": len(self.fills),
            "simulation": crypto_sim_assumptions(),
        }

    def save(self, path: Optional[str] = None) -> None:
        assert_crypto_paper_only()
        p = Path(path or CRYPTO_STATE_PATH)
        p.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": self.schema,
            "session_id": self.session_id,
            "base_currency": self.base_currency,
            "live_execution": False,
            "initial_capital": self.initial_capital,
            "cash": self.cash,
            "realized_pnl": self.realized_pnl,
            "fees_paid": self.fees_paid,
            "positions": {k: asdict(v) for k, v in self.positions.items()},
            "fills": self.fills,
            "applied_keys": sorted(self.applied_keys),
        }
        p.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Optional[str] = None) -> "CryptoPaperLedger":
        assert_crypto_paper_only()
        p = Path(path or CRYPTO_STATE_PATH)
        if not p.exists():
            return cls()
        raw = json.loads(p.read_text(encoding="utf-8"))
        led = cls(
            initial_capital=float(raw.get("initial_capital") or CRYPTO_INITIAL_CAPITAL_USDT),
            cash=float(raw.get("cash") or 0),
            realized_pnl=float(raw.get("realized_pnl") or 0),
            fees_paid=float(raw.get("fees_paid") or 0),
            session_id=str(raw.get("session_id") or ""),
        )
        for sym, row in (raw.get("positions") or {}).items():
            led.positions[sym] = CryptoPosition(
                symbol=str(row["symbol"]),
                qty=float(row["qty"]),
                avg_entry=float(row["avg_entry"]),
                entry_timestamp=str(row.get("entry_timestamp") or ""),
                signal_id=str(row.get("signal_id") or ""),
            )
        led.fills = list(raw.get("fills") or [])
        led.applied_keys = set(raw.get("applied_keys") or [])
        led.live_execution = False
        return led

    @classmethod
    def new_session(cls, capital: Optional[float] = None) -> "CryptoPaperLedger":
        assert_crypto_paper_only()
        c = float(capital if capital is not None else CRYPTO_INITIAL_CAPITAL_USDT)
        return cls(initial_capital=c, cash=c)
