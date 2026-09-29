"""Crypto strategy lifecycle status — independent of IDX promotion.

Statuses:
  RESEARCH              — experimentation only; paper ops requires explicit allow flag
  CANDIDATE             — passed evidence thresholds (PromotionGate approved)
  PAPER_ALLOWED         — ops paper path may use without research flag
  REJECTED              — blocked from paper ops

RESEARCH is never silently treated as PROMOTED / PAPER_ALLOWED.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

DEFAULT_STATUS_PATH = os.getenv(
    "CRYPTO_STRATEGY_STATUS_PATH", "state/crypto/strategy_status.json"
)


@dataclass
class StrategyStatusRecord:
    strategy_id: str
    strategy_version: str
    status: str
    reasons: list[str]
    evidence_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "status": self.status,
            "reasons": list(self.reasons),
            "evidence_hash": self.evidence_hash,
        }


def load_status_store(path: Optional[str] = None) -> dict[str, Any]:
    p = Path(path or DEFAULT_STATUS_PATH)
    if not p.exists():
        return {"strategies": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"strategies": {}}


def save_status_store(store: dict[str, Any], path: Optional[str] = None) -> None:
    p = Path(path or DEFAULT_STATUS_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(store, indent=2), encoding="utf-8")


def _key(strategy_id: str, strategy_version: str) -> str:
    return f"{strategy_id}@{strategy_version}"


def get_status(
    strategy_id: str,
    strategy_version: str,
    *,
    path: Optional[str] = None,
) -> StrategyStatusRecord:
    store = load_status_store(path)
    row = (store.get("strategies") or {}).get(_key(strategy_id, strategy_version))
    if not row:
        return StrategyStatusRecord(
            strategy_id, strategy_version, "RESEARCH", ["DEFAULT_RESEARCH"]
        )
    return StrategyStatusRecord(
        strategy_id=strategy_id,
        strategy_version=strategy_version,
        status=str(row.get("status") or "RESEARCH"),
        reasons=list(row.get("reasons") or []),
        evidence_hash=str(row.get("evidence_hash") or ""),
    )


def set_status(rec: StrategyStatusRecord, *, path: Optional[str] = None) -> None:
    store = load_status_store(path)
    store.setdefault("strategies", {})
    store["strategies"][_key(rec.strategy_id, rec.strategy_version)] = rec.to_dict()
    save_status_store(store, path)


def paper_ops_allowed(
    strategy_id: str,
    strategy_version: str,
    *,
    path: Optional[str] = None,
    allow_research_experiment: Optional[bool] = None,
) -> tuple[bool, str]:
    rec = get_status(strategy_id, strategy_version, path=path)
    if rec.status == "REJECTED":
        return False, "REJECTED"
    if rec.status == "PAPER_ALLOWED":
        return True, "PAPER_ALLOWED"
    if rec.status == "CANDIDATE":
        return True, "CANDIDATE_PAPER"
    if allow_research_experiment is None:
        allow_research_experiment = os.getenv(
            "CRYPTO_ALLOW_RESEARCH_PAPER", "1"
        ).strip() not in ("0", "false", "FALSE", "no")
    if allow_research_experiment:
        return True, "RESEARCH_EXPERIMENTATION"
    return False, "RESEARCH_REQUIRES_FLAG"
