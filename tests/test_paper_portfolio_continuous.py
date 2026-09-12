from __future__ import annotations
from pathlib import Path
import json
from src.python.ops.paper_portfolio import (
    DEFAULT_INITIAL_CAPITAL, PaperPortfolioStore, apply_long_entry, new_session,
)

def test_default_capital_10m():
    st = new_session()
    assert st.initial_capital == 10_000_000.0
    assert DEFAULT_INITIAL_CAPITAL == 10_000_000.0

def test_persist_restore_position(tmp_path):
    store = PaperPortfolioStore(tmp_path / "pp.json")
    st = new_session()
    st, trade, cls = apply_long_entry(st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="sig1", timestamp="2026-09-01", fee_bps=0, slippage_bps=0)
    assert cls == "FULL_FILL" and trade is not None
    cash_after = st.cash
    store.save_atomic(st)
    st2 = store.load()
    assert st2.cash == cash_after and "BBCA" in st2.open_positions()

def test_day2_existing_position_skip(tmp_path):
    store = PaperPortfolioStore(tmp_path / "pp.json")
    st = new_session()
    st, _, cls1 = apply_long_entry(st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="sig1", timestamp="d1", fee_bps=0, slippage_bps=0)
    store.save_atomic(st)
    st = store.load()
    st, _, cls2 = apply_long_entry(st, symbol="BBCA", price=9100.0, weight=0.10, signal_id="sig2", timestamp="d2", fee_bps=0, slippage_bps=0)
    assert cls1 == "FULL_FILL" and cls2 == "SKIPPED_EXISTING_POSITION"

def test_reset_new_session(tmp_path):
    store = PaperPortfolioStore(tmp_path / "pp.json", archive_dir=tmp_path / "sessions")
    st = new_session()
    st, _, _ = apply_long_entry(st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="s1", timestamp="d1", fee_bps=0, slippage_bps=0)
    store.save_atomic(st)
    old_id = st.simulation_session_id
    _, new = store.archive_and_reset()
    assert new.cash == 10_000_000.0 and new.open_positions() == {} and new.simulation_session_id != old_id

def test_signal_bot_smoke(tmp_path):
    from typer.testing import CliRunner
    from src.python.ops.signal_bot import app
    r = CliRunner().invoke(app, ["--mode", "TEST", "--force-schedule",
        "--state-dir", str(tmp_path/"state"), "--artifact-dir", str(tmp_path/"art"), "--symbols", "BBCA"])
    assert r.exit_code == 0, r.output
    assert (tmp_path/"state"/"paper_portfolio.json").exists()

def test_workflow_has_reset():
    yml = Path(".github/workflows/idx_signal.yml").read_text()
    assert "reset_portfolio" in yml and "idx-operational" in yml
