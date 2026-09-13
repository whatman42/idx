"""Train diverse lightweight candidates under Governor (no auto-promote)."""
from __future__ import annotations
import json
import os
from pathlib import Path
import typer
from src.python.market.providers import SyntheticProvider
from src.python.ml.pipeline import run_lightweight_training

app = typer.Typer()

@app.command()
def main(
    out_dir: str = typer.Option("models/candidates"),
    min_oos_accuracy: float = typer.Option(0.0),
    promote: bool = typer.Option(False),
    budget_sec: float = typer.Option(600.0),
    symbols: str = typer.Option("BBCA,BBRI,TLKM,ASII,ICBP"),
):
    csv = os.getenv("IDX_CSV_PATH", "data/ops/ohlcv.csv")
    if csv and Path(csv).exists():
        import pandas as pd
        bars = pd.read_csv(csv)
        if "timestamp" in bars.columns:
            bars["timestamp"] = pd.to_datetime(bars["timestamp"])
        source = f"csv:{csv}"
    else:
        syms = [s.strip() for s in symbols.split(",") if s.strip()]
        c = SyntheticProvider(n=120, seed=42).fetch(syms)
        bars, source = c.df, c.source
    report = run_lightweight_training(bars, out_dir=out_dir, budget_sec=budget_sec)
    report["data_source"] = source
    report["promote_requested"] = bool(promote)
    report["promoted"] = False
    if min_oos_accuracy > 0:
        for r in report.get("results") or []:
            acc = float((r.get("metrics") or {}).get("accuracy") or 0)
            r["meets_min_oos_accuracy"] = acc >= min_oos_accuracy
    print(json.dumps(report, indent=2, default=str))

if __name__ == "__main__":
    app()
