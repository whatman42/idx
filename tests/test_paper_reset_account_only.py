from __future__ import annotations
import hashlib, json
from pathlib import Path
from src.python.ops.paper_portfolio import (
    DEFAULT_INITIAL_CAPITAL, PaperPortfolioStore, apply_long_entry, new_session, paper_reset_scope,
)
from src.python.registry.artifacts import find_production_version, promote_to_production

def _write(path: Path, content: bytes | str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content if isinstance(content, bytes) else content.encode()
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()

def test_paper_reset_scope_declaration():
    scope = paper_reset_scope()
    assert scope["resets"] == "PAPER_ACCOUNT_STATE_ONLY"
    assert "retrain" in scope["does_not"]

def test_reset_preserves_model_and_pointer(tmp_path):
    root = tmp_path / "ws"
    models = root / "models"
    model_path = models / "primary" / "model.bin"
    h_model = _write(model_path, b"fake-weights")
    promote_to_production(models / "primary", "primary", "v1")
    prod_ptr = models / "primary" / "primary.PRODUCTION"
    h_ptr = hashlib.sha256(prod_ptr.read_bytes()).hexdigest()
    store = PaperPortfolioStore(root / "state" / "ops" / "paper_portfolio.json",
                                archive_dir=root / "state" / "ops" / "sessions")
    st = new_session()
    st, _, _ = apply_long_entry(st, symbol="BBCA", price=9000.0, weight=0.10, signal_id="s1", timestamp="d1", fee_bps=0, slippage_bps=0)
    store.save_atomic(st)
    store.archive_and_reset()
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == h_model
    assert hashlib.sha256(prod_ptr.read_bytes()).hexdigest() == h_ptr
    assert find_production_version(models / "primary", "primary") == "v1"

def test_reset_cli_preserves_intelligence(tmp_path):
    from typer.testing import CliRunner
    from src.python.ops.signal_bot import app
    marker = tmp_path / "models" / "candidates" / "sentinel.txt"
    marker.parent.mkdir(parents=True)
    marker.write_text("pre-reset")
    r = CliRunner().invoke(app, ["--mode", "TEST", "--force-schedule", "--reset-portfolio",
        "--state-dir", str(tmp_path/"state"), "--artifact-dir", str(tmp_path/"art"), "--symbols", "BBCA"])
    assert r.exit_code == 0, r.output
    out = json.loads(r.output)
    assert out["status"] == "PORTFOLIO_RESET"
    assert out["retrain_triggered"] is False
    assert out["production_pointer_changed"] is False
    assert out["intelligence_state"] == "PRESERVED"
    assert marker.read_text() == "pre-reset"
