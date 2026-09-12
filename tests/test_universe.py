from pathlib import Path
from src.python.market.universe import load_universe, resolve_symbols

def test_universe_file_exists():
    assert Path("data/universe/idx_symbols.json").exists()

def test_load_full_universe():
    syms = load_universe()
    assert len(syms) >= 500
    assert "BBCA" in syms and "TLKM" in syms

def test_resolve_all():
    assert len(resolve_symbols("ALL")) >= 500
    assert len(resolve_symbols("FULL")) >= 500
    assert resolve_symbols("BBCA,BBRI") == ["BBCA", "BBRI"]
