# IDX — Signal Engine + Paper Portfolio

**Signal-only** system for Indonesian IDX equities (paper simulation).

| Gate | Status |
|------|--------|
| Signal pipeline | OPS_READY |
| Paper portfolio (Rp10M) | READY |
| Universe scan | **FULL ~939 tickers** (public listing, not official BEI) |
| Public OHLCV (yfinance) | PUBLIC_RESEARCH |
| Cost model | UNVERIFIED_ASSUMPTION |
| Economic edge | UNVERIFIED |
| Live trading | NOT_SUPPORTED |
| production_ready_100pct | false |

## Full IDX universe scan

Default `symbols=ALL` loads `data/universe/idx_symbols.json` (~939 codes).

```bash
pip install -r requirements.txt
pytest -q
python -m src.python.ops.fetch_ohlcv --symbols ALL --period 3mo
python -m src.python.ops.signal_bot --mode PAPER --force-schedule --symbols ALL
```

- Telegram: top `IDX_MAX_NOTIFY_SIGNALS` (default 20)
- Paper entries: top `IDX_MAX_PORTFOLIO_ENTRIES` (default 15)
- Weight per new entry: 5% equity (full-universe mode)

## Workflow

`.github/workflows/idx_signal.yml` — Mon–Fri 16:30 WIB, timeout 45m.
PAPER/OPERATIONAL fetches full-universe OHLCV before the bot.

## Telegram narration (Gemini 3.5 Flash-Lite)

Every Telegram message (signals, **no signal**, halt) is narrated by Gemini.

Secrets / vars:
- `GEMINI_API_KEY` (required for live narration; otherwise template fallback)
- `GEMINI_MODEL` (default `gemini-3.5-flash-lite`)
- `IDX_TELEGRAM_ALLOW_PAPER=1` to allow PAPER-mode Telegram

Narrator is **advisory only** — does not change signals, portfolio, or production pointer.

## Compute surfaces

| Surface | Role |
|---------|------|
| GitHub Actions | Daily **operational** signals + paper portfolio (`ops_sma_v0`) |
| [Google Colab](colab/IDX_GPU_TRAINING.ipynb) | Weekend/heavy **candidate** training (Governor-gated, no auto-promote) |
| Telegram | Notifications only |

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/whatman42/idx/blob/main/colab/IDX_GPU_TRAINING.ipynb)

- Default training budget: `COLAB_TRAINING_BUDGET_SEC=1200`
- GPU is **optional**; CPU fallback is always supported
- Economic edge remains **UNVERIFIED** until valid forward/OOS evidence
