"""Fetch public research OHLCV for ops — defaults to FULL IDX universe."""
from __future__ import annotations
import json
import typer
from src.python.market.universe import resolve_symbols, universe_meta
from src.python.market.yfinance_provider import fetch_and_save_csv

app = typer.Typer()

@app.command()
def main(
    symbols: str = typer.Option("ALL", help="ALL|FULL = entire IDX universe, or comma list"),
    out: str = typer.Option("data/ops/ohlcv.csv"),
    period: str = typer.Option("3mo"),
    batch_size: int = typer.Option(80),
    universe_path: str = typer.Option("data/universe/idx_symbols.json"),
):
    meta_u = universe_meta(universe_path)
    syms = resolve_symbols(symbols, universe_path=universe_path)
    print(json.dumps({
        "universe_source": meta_u.get("source"),
        "universe_count": meta_u.get("count"),
        "symbols_resolved": len(syms),
        "period": period,
    }, indent=2))
    meta = fetch_and_save_csv(syms, out, period=period, batch_size=batch_size)
    meta["universe_source"] = meta_u.get("source")
    meta["universe_count"] = meta_u.get("count")
    print(json.dumps(meta, indent=2))

if __name__ == "__main__":
    app()
