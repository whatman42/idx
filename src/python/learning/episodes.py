"""Episode factory + idempotent store — Paper Fill → SignalEpisode bridge.

Research/control plane ONLY. Never executes trades or mutates production.

Guarantees:
  ONE closed fill (exit trade) → exactly ONE episode
  Retries with same idempotency_key do NOT create duplicates
  Missing exit → lifecycle INVALID (never silently COMPLETED)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from src.python.learning.contracts import (
    EpisodeLifecycle,
    EpisodeOutcome,
    SignalEpisode,
)


def make_idempotency_key(
    *,
    signal_id: str,
    symbol: str,
    entry_trade_id: str,
    exit_trade_id: str,
    session_id: str = "",
) -> str:
    """Deterministic hash of canonical trade identity."""
    raw = f"{session_id}|{signal_id}|{symbol}|{entry_trade_id}|{exit_trade_id}"
    return "ik_" + hashlib.sha256(raw.encode()).hexdigest()[:24]


def make_episode_id(idempotency_key: str) -> str:
    return "ep_" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:20]


def _outcome_from_pnl(pnl: float, *, flat_tol: float = 1.0) -> str:
    if abs(pnl) <= flat_tol:
        return EpisodeOutcome.FLAT.value
    return EpisodeOutcome.WIN.value if pnl > 0 else EpisodeOutcome.LOSS.value


def _r_multiple(entry_px: float, exit_px: float, sl_px: float, side: int = 1) -> float:
    if entry_px <= 0:
        return 0.0
    risk = abs(entry_px - sl_px) if sl_px and sl_px > 0 else entry_px * 0.03
    if risk <= 0:
        return 0.0
    if side >= 0:
        return (exit_px - entry_px) / risk
    return (entry_px - exit_px) / risk


def episode_from_closed_trade(
    exit_trade: dict[str, Any],
    *,
    entry_trade: Optional[dict[str, Any]] = None,
    strategy_id: str = "rule_sma20",
    strategy_version: str = "1.0",
    regime: str = "unknown",
    confidence: float = 0.0,
    score: float = 0.0,
    ensemble_votes: Optional[dict[str, float]] = None,
    feature_snapshot: Optional[dict[str, float]] = None,
    session_id: str = "",
    risk_decision: str = "ALLOW",
    governor_decision: str = "BUY",
) -> SignalEpisode:
    """Build SignalEpisode from a paper exit (SELL) trade. Exit-only chronology."""
    action = str(exit_trade.get("action", "")).upper()
    status = str(exit_trade.get("status", "")).upper()
    symbol = str(exit_trade.get("symbol") or "")
    exit_trade_id = str(exit_trade.get("trade_id") or "")
    signal_id = str(exit_trade.get("signal_id") or (entry_trade or {}).get("signal_id") or "")
    entry_trade_id = str((entry_trade or {}).get("trade_id") or "")

    if action not in ("SELL", "EXIT") or status not in ("FILLED", "FULL_EXIT", ""):
        ik = make_idempotency_key(
            signal_id=signal_id, symbol=symbol,
            entry_trade_id=entry_trade_id, exit_trade_id=exit_trade_id or "none",
            session_id=session_id,
        )
        return SignalEpisode(
            episode_id=make_episode_id(ik),
            trading_date=str(exit_trade.get("timestamp", ""))[:10],
            symbol=symbol,
            strategy_id=strategy_id,
            lifecycle=EpisodeLifecycle.INVALID.value,
            outcome=EpisodeOutcome.SKIPPED.value,
            signal_id=signal_id,
            fill_id=exit_trade_id,
            entry_trade_id=entry_trade_id,
            idempotency_key=ik,
            meta={"reason": "not_a_closed_exit_fill"},
        )

    entry_px = float(exit_trade.get("entry") or (entry_trade or {}).get("fill_price") or 0)
    exit_px = float(exit_trade.get("fill_price") or exit_trade.get("price") or 0)
    pnl = float(exit_trade.get("pnl") or 0)
    qty = float(exit_trade.get("qty") or 0)
    cost_basis = float(exit_trade.get("cost_basis") or (qty * entry_px if entry_px else 0))
    fees = float(exit_trade.get("fee") or 0) + float((entry_trade or {}).get("fee") or 0)
    sl_px = float(exit_trade.get("sl") or 0)
    tp_px = float(exit_trade.get("tp") or 0)
    exit_reason = str(exit_trade.get("reason") or "")
    ts = str(exit_trade.get("timestamp") or "")

    if entry_px <= 0 or exit_px <= 0 or not symbol:
        ik = make_idempotency_key(
            signal_id=signal_id, symbol=symbol,
            entry_trade_id=entry_trade_id, exit_trade_id=exit_trade_id,
            session_id=session_id,
        )
        return SignalEpisode(
            episode_id=make_episode_id(ik),
            trading_date=ts[:10],
            symbol=symbol,
            strategy_id=strategy_id,
            lifecycle=EpisodeLifecycle.INVALID.value,
            outcome=EpisodeOutcome.SKIPPED.value,
            signal_id=signal_id,
            fill_id=exit_trade_id,
            entry_trade_id=entry_trade_id,
            idempotency_key=ik,
            pnl=pnl,
            meta={"reason": "missing_prices_or_symbol"},
        )

    ik = make_idempotency_key(
        signal_id=signal_id, symbol=symbol,
        entry_trade_id=entry_trade_id or exit_trade_id,
        exit_trade_id=exit_trade_id,
        session_id=session_id,
    )
    r_mult = _r_multiple(entry_px, exit_px, sl_px, side=1)
    outcome = _outcome_from_pnl(pnl)

    return SignalEpisode(
        episode_id=make_episode_id(ik),
        trading_date=ts[:10],
        symbol=symbol,
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        regime=regime,
        side=1,
        confidence=float(confidence),
        score=float(score),
        ensemble_votes=dict(ensemble_votes or {}),
        feature_snapshot=dict(feature_snapshot or {}),
        risk_decision=risk_decision,
        governor_decision=governor_decision,
        entry_px=entry_px,
        exit_px=exit_px,
        exit_reason=exit_reason,
        r_multiple=float(r_mult),
        pnl=float(pnl),
        outcome=outcome,
        signal_id=signal_id,
        fill_id=exit_trade_id,
        entry_trade_id=entry_trade_id,
        idempotency_key=ik,
        lifecycle=EpisodeLifecycle.COMPLETED.value,
        qty=qty,
        cost_basis=cost_basis,
        fees=fees,
        meta={
            "tp": tp_px,
            "sl": sl_px,
            "exit_method": exit_trade.get("exit_method"),
            "session_id": session_id,
        },
    )


def pair_entry_for_exit(
    trades: list[dict[str, Any]],
    exit_trade: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Find matching BUY entry for an exit by signal_id or symbol (latest prior)."""
    signal_id = str(exit_trade.get("signal_id") or "")
    symbol = str(exit_trade.get("symbol") or "")
    exit_ts = str(exit_trade.get("timestamp") or "")
    candidates = []
    for tr in trades:
        if str(tr.get("action", "")).upper() != "BUY":
            continue
        if str(tr.get("status", "")).upper() not in ("FILLED", "FULL_FILL", ""):
            continue
        if signal_id and str(tr.get("signal_id") or "") == signal_id:
            candidates.append(tr)
        elif not signal_id and str(tr.get("symbol") or "") == symbol:
            if str(tr.get("timestamp") or "") <= exit_ts:
                candidates.append(tr)
    if not candidates:
        return None
    return candidates[-1]


class EpisodeStore:
    """Idempotent episode ledger. Prefer path under state/learning/ (paper-reset protected)."""

    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path) if path else None
        self._by_key: dict[str, SignalEpisode] = {}
        if self.path and self.path.exists():
            self._load()

    def _load(self) -> None:
        assert self.path is not None
        data = json.loads(self.path.read_text())
        for row in data.get("episodes", []):
            known = {k: row[k] for k in SignalEpisode.__dataclass_fields__ if k in row}
            ep = SignalEpisode(**known)
            if ep.idempotency_key:
                self._by_key[ep.idempotency_key] = ep

    def _save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "episodes": [e.to_dict() for e in self._by_key.values()],
            "count": len(self._by_key),
            "immutable_keys": True,
        }
        self.path.write_text(json.dumps(payload, indent=2, default=str))

    def has(self, idempotency_key: str) -> bool:
        return idempotency_key in self._by_key

    def get(self, idempotency_key: str) -> Optional[SignalEpisode]:
        return self._by_key.get(idempotency_key)

    def upsert(self, ep: SignalEpisode) -> tuple[SignalEpisode, bool]:
        """Insert if new. Returns (episode, created). Same key → no duplicate."""
        if not ep.idempotency_key:
            raise ValueError("episode requires idempotency_key")
        if ep.idempotency_key in self._by_key:
            return self._by_key[ep.idempotency_key], False
        self._by_key[ep.idempotency_key] = ep
        self._save()
        return ep, True

    def list_completed(self) -> list[SignalEpisode]:
        return [
            e for e in self._by_key.values()
            if e.lifecycle in (EpisodeLifecycle.COMPLETED.value, EpisodeLifecycle.ATTRIBUTED.value)
        ]

    def list_all(self) -> list[SignalEpisode]:
        return list(self._by_key.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": len(self._by_key),
            "episodes": [e.to_dict() for e in self._by_key.values()],
        }


def ingest_closed_trades_from_portfolio(
    trades: list[dict[str, Any]],
    *,
    store: EpisodeStore,
    strategy_id: str = "rule_sma20",
    strategy_version: str = "1.0",
    session_id: str = "",
    regime: str = "unknown",
) -> dict[str, Any]:
    """Ingest all SELL fills into EpisodeStore. Idempotent. Research only."""
    created = 0
    skipped = 0
    invalid = 0
    episodes: list[dict[str, Any]] = []
    for tr in trades:
        action = str(tr.get("action", "")).upper()
        if action not in ("SELL", "EXIT"):
            continue
        entry = pair_entry_for_exit(trades, tr)
        ep = episode_from_closed_trade(
            tr,
            entry_trade=entry,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            session_id=session_id,
            regime=regime,
        )
        stored, was_new = store.upsert(ep)
        if ep.lifecycle == EpisodeLifecycle.INVALID.value:
            if was_new:
                invalid += 1
            else:
                skipped += 1
        elif was_new:
            created += 1
            episodes.append(stored.to_dict())
        else:
            skipped += 1
    return {
        "created": created,
        "skipped_duplicates": skipped,
        "invalid": invalid,
        "total_in_store": len(store.list_all()),
        "new_episodes": episodes,
        "principle": "research_only_no_execution",
    }
