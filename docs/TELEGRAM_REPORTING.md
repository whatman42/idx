# Telegram signal reporting — financial integrity contract

## SIGNAL_ONLY

- `signal_only=true`, `live_execution=false` always on `CycleReport`
- No broker execution path
- Exactly-once delivery is **not** claimed; idempotency is best-effort via notify ledger

## Single source of truth

All Telegram numbers are rendered from:

- `SignalReport`
- `PortfolioSnapshot` / `OpenPositionView`
- `ExitReport`
- `CycleReport`

Module: `src/python/reporting/`

Composer **must not** recompute financial fields.

## Lot / share convention

**1 lot = 100 shares** (`SHARES_PER_LOT`)

| Formula | Definition |
|---------|------------|
| shares | lots × 100 |
| position_value | entry_price × shares |
| exposure_pct | position_value / equity × 100 |
| risk_amount | \|entry − SL\| × shares |
| risk_pct | risk_amount / equity × 100 |
| RR (long) | (TP − entry) / (entry − SL) |
| uPnL (long) | (mark − entry) × shares |
| realized (long) | (exit − entry) × shares |

Golden regression (must never regress):

- Equity 10_120_000, BBCA 5 lot @ 9_850 mark 9_900  
- shares=500, position_value=4_925_000, uPnL=25_000, exposure≈48.67%

## Confidence

Stored as **0–100 model score**, not calibrated probability.

Wording: `Model confidence: 72/100`  
Field `confidence_method` is mandatory (e.g. `sma20_rank_score`).

## LLM boundary

1. Deterministic composer always available  
2. Optional Gemini narration is language-only  
3. `validate_llm_output` rejects decision/symbol/id/numeric mutations  
4. On failure → deterministic fallback  

LLM must not decide BUY/SELL/NO_SIGNAL or change numbers.

## Validation (fail-closed)

- `validate_position_math`
- `validate_portfolio_math`
- `validate_exit_report`
- `validate_signal_report`
- `validate_cycle_report`
- `validate_telegram_payload`
- `validate_llm_output`

Integrity failure produces an explicit DATA INTEGRITY FAILURE message, not a fake valid signal.

## Exit reports

Only from trade journal records (entry, exit, qty/lots, PnL, reason, timestamp).

## Tests

See `tests/test_reporting_integrity.py` (BBCA golden, recon, LLM mutation, 1000-cycle soak of formulas).
