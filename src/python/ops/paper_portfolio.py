"""Instant Paper Portfolio — simulated fills only, NO broker execution.

Schema ops_paper_v2 + TP/SL + performance metrics + ledger reconstruction.
NO LIVE EXECUTION. Broker is never used for orders.
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
        "note": "Simulation assumptions only; not real broker tariffs",
    }
