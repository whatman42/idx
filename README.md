# IDX — Production Signal Engine + Paper Portfolio

**Signal-only** quantitative system for Indonesian IDX equities.

| Status | Value |
|--------|--------|
| Signal engine | PRODUCTION_SIGNAL_READY |
| Paper portfolio | PAPER_PORTFOLIO_READY (Rp10,000,000 default) |
| Economic edge | ECONOMIC_EDGE_UNVERIFIED |
| Live trading | NOT_SUPPORTED |

## Architecture

- **GitHub Actions** — daily signal operate (Mon–Fri 16:30 Asia/Jakarta)
- **Google Colab** — weekend training only (<20 min)
- **Telegram** — output only
- **Paper portfolio** — continuous multi-day simulation; reset = account only

## Quick start

```bash
pip install -r requirements.txt
pytest -q
python -m src.python.ops.signal_bot --mode TEST --force-schedule
```

## Workflow

`.github/workflows/idx_signal.yml` — schedule `30 9 * * 1-5` (09:30 UTC = 16:30 WIB)

Secrets: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`  
Data: free/public OHLCV at `data/ops/ohlcv.csv` or `IDX_CSV_PATH`
