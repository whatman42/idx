# Market Structure / FCA Gate (Policy A)

FCA is a **market-structure constraint**, not a cosmetic screener flag.

```
AUTHORITATIVE MARKET STATUS
        ↓
FCA / HALT / UNKNOWN DETECTION
        ↓
… Strategy → Risk → Governor …
        ↓
MARKET STRUCTURE EXECUTION GATE  (second check)
        ↓
OrderIntent (paper) | BLOCK
```

## Enum (not bool)

`CONTINUOUS | FCA | HALTED | SUSPENDED | UNKNOWN`

`UNKNOWN ≠ CONTINUOUS` → **BLOCK** (fail-closed).

## Policy A (baseline)

| Mode | Order intent |
|------|----------------|
| CONTINUOUS (fresh) | may continue if other gates pass |
| FCA | **BLOCK** (`FCA_INSTRUMENT`) |
| HALTED / SUSPENDED | **BLOCK** |
| UNKNOWN / stale / missing | **BLOCK** |

No permanent FCA list hardcoded in strategy logic — use versioned metadata provider.

## Forbidden

- Detect FCA from price/volume alone as sole authority
- Gemini/Telegram as operational truth
- Broker send on blocked structure

## Module

`src/python/market_structure/` — models, provider, freshness, policy, gate

LIVE_EXECUTION / BROKER_EXECUTION remain **FALSE**.
