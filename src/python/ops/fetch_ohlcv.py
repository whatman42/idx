"""Fetch public research OHLCV for ops."""
from __future__ import annotations
import json
import typer
from src.python.market.yfinance_provider import fetch_and_save_csv

app = typer.Typer()

@app.command()
def main(
    symbols: str = typer.Option("BBCA,BBRI,TLKM"),
    out: str = typer.Option("data/ops/ohlcv.csv"),
    period: str = typer.Option("6mo"),
):
    syms = [s.strip() for s in symbols.split(",") if s.strip()]
    meta = fetch_and_save_csv(syms, out, period=period)
    print(json.dumps(meta, indent=2))

if __name__ == "__main__":
    app()
