# IDX — Signal Engine + Paper Portfolio

**Signal-only** system for Indonesian IDX equities (paper simulation).

| Gate | Status |
|------|--------|
| Signal pipeline | OPS_READY |
| Paper portfolio (Rp10M) | READY |
| Public OHLCV (yfinance) | PUBLIC_RESEARCH (not official BEI) |
| Cost model | UNVERIFIED_ASSUMPTION |
| Economic edge | UNVERIFIED |
| Live trading | NOT_SUPPORTED |
| **production_ready_100pct** | **false** until edge + verified costs + ops data |

## Honest policy

`production_ready` / `production_ready_100pct` stay **false** until:
1. Operational (non-synthetic) data + DQ PASS + freshness PASS  
2. Cost model VERIFIED against real market assumptions you accept  
3. Economic edge DEMONSTRATED net of costs  

Positive paper PnL on synthetic or unverified costs is **not** 100% ready.

## Quick start

```bash
pip install -r requirements.txt
pytest -q
python -m src.python.ops.fetch_ohlcv --symbols BBCA,BBRI,TLKM --out data/ops/ohlcv.csv
python -m src.python.ops.signal_bot --mode PAPER --force-schedule --csv data/ops/ohlcv.csv
```

## Workflow

`.github/workflows/idx_signal.yml` — Mon–Fri 09:30 UTC (16:30 WIB).  
PAPER/OPERATIONAL fetches yfinance OHLCV before the bot. Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
