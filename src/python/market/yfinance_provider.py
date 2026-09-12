"""Public free OHLCV provider via yfinance.

NOT official BEI data. auto_adjust=True. Full-universe batch download.
"""
from __future__ import annotations

import hashlib
import time
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


def _bare(sym: str) -> str:
    return str(sym).strip().upper().replace(".JK", "")


@dataclass
class YFinanceProvider:
    period: str = "6mo"
    interval: str = "1d"
    auto_adjust: bool = True
    batch_size: int = 80
    batch_pause_sec: float = 0.5

    def fetch(self, symbols: Sequence[str]) -> DataContract:
        try:
            import yfinance as yf
        except ImportError as e:
            raise RuntimeError("yfinance not installed; pip install yfinance") from e
        symbols = list(dict.fromkeys(_bare(s) for s in symbols))
        frames: list[pd.DataFrame] = []
        failed: list[str] = []
        for i in range(0, len(symbols), self.batch_size):
            batch = symbols[i : i + self.batch_size]
            ysyms = [_to_yf_symbol(s) for s in batch]
            try:
                data = yf.download(
                    tickers=" ".join(ysyms),
                    period=self.period,
                    interval=self.interval,
                    auto_adjust=self.auto_adjust,
                    group_by="ticker",
                    threads=False,  # avoid yfinance sqlite "database is locked"
                    progress=False,
                )
            except Exception:
                data = None
            if data is None or data.empty:
                for s, ys in zip(batch, ysyms):
                    try:
                        hist = yf.Ticker(ys).history(
                            period=self.period, interval=self.interval, auto_adjust=self.auto_adjust
                        )
                        if hist is None or hist.empty:
                            failed.append(s)
                            continue
                        hist = hist.reset_index()
                        ts_col = "Date" if "Date" in hist.columns else hist.columns[0]
                        frames.append(pd.DataFrame({
                            "timestamp": pd.to_datetime(hist[ts_col]).dt.tz_localize(None),
                            "symbol": s,
                            "open": hist["Open"].astype(float),
                            "high": hist["High"].astype(float),
                            "low": hist["Low"].astype(float),
                            "close": hist["Close"].astype(float),
                            "volume": hist["Volume"].fillna(0).astype(float),
                        }))
                    except Exception:
                        failed.append(s)
            else:
                if isinstance(data.columns, pd.MultiIndex):
                    tickers_in = data.columns.get_level_values(0).unique()
                    for ys in ysyms:
                        bare = _bare(ys)
                        key = None
                        for t in tickers_in:
                            if _bare(str(t)) == bare:
                                key = t
                                break
                        if key is None:
                            failed.append(bare)
                            continue
                        try:
                            sub = data[key].dropna(how="all")
                            if sub.empty:
                                failed.append(bare)
                                continue
                            sub = sub.reset_index()
                            ts_col = "Date" if "Date" in sub.columns else ("Datetime" if "Datetime" in sub.columns else sub.columns[0])
                            frames.append(pd.DataFrame({
                                "timestamp": pd.to_datetime(sub[ts_col]).dt.tz_localize(None),
                                "symbol": bare,
                                "open": sub["Open"].astype(float),
                                "high": sub["High"].astype(float),
                                "low": sub["Low"].astype(float),
                                "close": sub["Close"].astype(float),
                                "volume": sub["Volume"].fillna(0).astype(float) if "Volume" in sub.columns else 0.0,
                            }))
                        except Exception:
                            failed.append(bare)
                else:
                    bare = batch[0]
                    sub = data.reset_index()
                    ts_col = "Date" if "Date" in sub.columns else sub.columns[0]
                    frames.append(pd.DataFrame({
                        "timestamp": pd.to_datetime(sub[ts_col]).dt.tz_localize(None),
                        "symbol": bare,
                        "open": sub["Open"].astype(float),
                        "high": sub["High"].astype(float),
                        "low": sub["Low"].astype(float),
                        "close": sub["Close"].astype(float),
                        "volume": sub["Volume"].fillna(0).astype(float) if "Volume" in sub.columns else 0.0,
                    }))
            if self.batch_pause_sec and i + self.batch_size < len(symbols):
                time.sleep(self.batch_pause_sec)
        if not frames:
            raise RuntimeError(f"yfinance empty for all symbols (n={len(symbols)}) failed={failed[:20]}")
        df = pd.concat(frames, ignore_index=True)
        df = df.dropna(subset=["close"])
        df = df[df["close"] > 0]
        df = df.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        return DataContract(df=df, source="yfinance_public_research")


def fetch_and_save_csv(
    symbols: Sequence[str],
    out_path: str,
    period: str = "6mo",
    batch_size: int = 80,
) -> dict:
    from pathlib import Path
    provider = YFinanceProvider(period=period, batch_size=batch_size)
    contract = provider.fetch(symbols)
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    contract.df.to_csv(path, index=False)
    raw = path.read_bytes()
    return {
        "path": str(path),
        "source": contract.source,
        "rows": len(contract.df),
        "symbols_requested": len(symbols),
        "symbols_loaded": sorted(contract.df["symbol"].astype(str).unique().tolist()),
        "symbols_loaded_count": int(contract.df["symbol"].nunique()),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "official_bei": False,
        "status": "PUBLIC_RESEARCH_OHLCV",
        "universe_scan": True,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
    }
