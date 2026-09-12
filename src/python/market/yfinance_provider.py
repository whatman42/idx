"""Public free OHLCV provider via yfinance.

NOT official BEI data. auto_adjust=True. Suitable for paper/research ops only.
Status: PUBLIC_RESEARCH_OHLCV — never claim exchange-grade.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

import pandas as pd

from src.python.market.providers import DataContract


def _to_yf_symbol(sym: str) -> str:
    s = str(sym).strip().upper()
    if s.endswith(".JK"):
        return s
    return f"{s}.JK"


@dataclass
class YFinanceProvider:
    period: str = "6mo"
    interval: str = "1d"
    auto_adjust: bool = True

    def fetch(self, symbols: Sequence[str]) -> DataContract:
        try:
            import yfinance as yf
        except ImportError as e:
            raise RuntimeError("yfinance not installed; pip install yfinance") from e
        rows: list[dict] = []
        for raw in symbols:
            ysym = _to_yf_symbol(raw)
            bare = ysym.replace(".JK", "")
            t = yf.Ticker(ysym)
            hist = t.history(period=self.period, interval=self.interval, auto_adjust=self.auto_adjust)
            if hist is None or hist.empty:
                continue
            hist = hist.reset_index()
            ts_col = "Date" if "Date" in hist.columns else ("Datetime" if "Datetime" in hist.columns else hist.columns[0])
            for _, r in hist.iterrows():
                ts = pd.Timestamp(r[ts_col])
                if getattr(ts, "tzinfo", None) is not None:
                    ts = ts.tz_localize(None)
                rows.append({
                    "timestamp": ts,
                    "symbol": bare,
                    "open": float(r["Open"]),
                    "high": float(r["High"]),
                    "low": float(r["Low"]),
                    "close": float(r["Close"]),
                    "volume": float(r.get("Volume", 0) or 0),
                })
        if not rows:
            raise RuntimeError(f"yfinance returned empty for symbols={list(symbols)}")
        df = pd.DataFrame(rows).sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        return DataContract(df=df, source="yfinance_public_research")


def fetch_and_save_csv(symbols: Sequence[str], out_path: str, period: str = "6mo") -> dict:
    from pathlib import Path
    provider = YFinanceProvider(period=period)
    contract = provider.fetch(symbols)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    contract.df.to_csv(path, index=False)
    raw = path.read_bytes()
    return {
        "path": str(path),
        "source": contract.source,
        "rows": len(contract.df),
        "symbols": sorted(contract.df["symbol"].astype(str).unique().tolist()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "official_bei": False,
        "status": "PUBLIC_RESEARCH_OHLCV",
        "fetched_at": datetime.utcnow().isoformat() + "Z",
    }
