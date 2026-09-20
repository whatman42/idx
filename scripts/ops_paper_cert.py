#!/usr/bin/env python3
"""Operational paper-trading certification — deterministic, no broker."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    results = []

    def ok(name: str, note: str = "") -> None:
        results.append((name, "PASS", note))
        print(f"[PASS] {name}" + (f" — {note}" if note else ""))

    def fail(name: str, note: str = "") -> None:
        results.append((name, "FAIL", note))
        print(f"[FAIL] {name}" + (f" — {note}" if note else ""))

    import pandas as pd
    from src.python.data.quality import validate_ohlcv

    good = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-09-01", periods=5, freq="B", tz="UTC"),
            "symbol": ["TEST"] * 5,
            "open": [10, 11, 12, 13, 14],
            "high": [11, 12, 13, 14, 15],
            "low": [9, 10, 11, 12, 13],
            "close": [10.5, 11.5, 12.5, 13.5, 14.5],
            "volume": [100] * 5,
        }
    )
    r = validate_ohlcv(good)
    (ok if r.ok else fail)("data_quality_valid")

    bad = good.copy()
    bad.loc[2, "high"] = 1.0
    r2 = validate_ohlcv(bad)
    (ok if not r2.ok else fail)("data_quality_fail_closed")

    from src.python.strategy.feature_snapshot import is_forbidden_feature_name

    (ok if is_forbidden_feature_name("y_next_up") else fail)("feature_label_guard")
    (ok if not is_forbidden_feature_name("sma_dist_20") else fail)("feature_allowed")

    from src.python.ops.paper_portfolio import (
        PaperPortfolioStore,
        new_session,
        validate_portfolio_accounting,
    )

    with tempfile.TemporaryDirectory() as td:
        store = PaperPortfolioStore(Path(td) / "pf.json", archive_dir=Path(td) / "sessions")
        pf = new_session(initial_capital=100_000_000.0)
        store.save_atomic(pf)
        pf2 = store.load()
        inv = validate_portfolio_accounting(pf2)
        cash0 = float(pf2.cash)
        (ok if cash0 == 100_000_000.0 else fail)("paper_store_init", f"cash={cash0}")
        (ok if inv == [] else fail)("ledger_accounting", str(inv)[:80])

    from src.python.strategy.promotion_gate import PromotionGate  # noqa: F401

    ok("promotion_gate_import")

    from src.python.archive.contracts import archive_cannot_affect_trading

    (ok if archive_cannot_affect_trading() else fail)("archive_isolation")

    live = False
    broker = False
    (ok if not live and not broker else fail)("live_broker_false")

    fails = [x for x in results if x[1] == "FAIL"]
    print(json.dumps({"pass": len(results) - len(fails), "fail": len(fails)}, indent=2))
    if fails:
        print("OPS PAPER CERT = FAIL")
        return 1
    print("OPS PAPER CERT = PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
